#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pysheds.grid import Grid
import seaborn as sns
from geopy.distance import geodesic
from rasterio.mask import mask
import re
import glob
import shutil
import os
import json
import numpy as np
import geopandas as gpd
from pysheds.sview import View
import warnings
import time
import os
import random
import string
import rasterio.features
import tempfile
import rasterio
from rasterio import features
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
from scipy import stats

from app.gis.watershed_core.parse_geojson_to_frontend import parse_geojson_to_frontend


warnings.filterwarnings("ignore")
sns.set_palette("pastel")
warnings.filterwarnings("ignore")
sns.set_palette("pastel")
# Import all functions from the existing test script

source_count = 0


####   1.河道追踪相关算法   ####
# 将点吸附到最近的河道像元
def snap_point_to_stream(x, y, identified_streams, grid, search_radius=10):
    """
    将点坐标吸附到最近的河道像元

    参数:
    x, y : float
        点的地理坐标
    identified_streams : array
        河道网络数组
    grid : Grid
        Grid对象
    search_radius : int
        搜索半径（像元数）

    返回:
    lon, lat, row, col : float, float, int, int
        吸附后的经纬度和行列坐标
    """
    # 将地理坐标转换为行列坐标
    col, row = grid.nearest_cell(x, y)

    # 检查点是否已经在河道上
    if (
        0 <= row < identified_streams.shape[0]
        and 0 <= col < identified_streams.shape[1]
        and identified_streams[row, col] == 1
    ):
        # 点已经在河道上，直接返回
        lon, lat = View.affine_transform(grid.affine, col, row)
        return lon, lat, row, col

    # 如果不在河道上，在周围搜索最近的河道像元
    min_distance = float("inf")
    closest_row, closest_col = None, None

    # 在搜索半径内查找最近的河道像元
    for dr in range(-search_radius, search_radius + 1):
        for dc in range(-search_radius, search_radius + 1):
            new_row, new_col = row + dr, col + dc

            # 检查是否在有效范围内
            if (
                0 <= new_row < identified_streams.shape[0]
                and 0 <= new_col < identified_streams.shape[1]
            ):

                # 检查是否在河道上
                if identified_streams[new_row, new_col] == 1:
                    # 计算距离
                    distance = np.sqrt(dr**2 + dc**2)
                    if distance < min_distance:
                        min_distance = distance
                        closest_row, closest_col = new_row, new_col
    
    # 返回结果
    if closest_row is not None and closest_col is not None:
        # 找到最近的河道像元
        lon, lat = View.affine_transform(grid.affine, closest_col, closest_row)
        print(f"吸附后的河道像元坐标:")
        print(f"  行列坐标: row={closest_row}, col={closest_col}")
        print(f"  经纬度坐标: lon={lon:.6f}, lat={lat:.6f}")
        return lon, lat, closest_row, closest_col
    else:
        # 未找到河道，返回原始坐标
        print("未找到附近的河道像元，返回原始坐标")
        return x, y, row, col


# 定义添加倾泻点到break_point.geojson文件的函数
def add_break_point(x, y, point_id=None):
    """
    将指定的倾泻点坐标添加到break_point.geojson文件中

    参数:
    x : float
        倾泻点的经度坐标
    y : float
        倾泻点的纬度坐标
    point_id : str or int, optional
        点的标识符，如果不提供则自动生成
    """

    # 文件名
    filename = "break_point.geojson"

    # 如果文件不存在，创建一个空的FeatureCollection
    if not os.path.exists(filename):
        data = {"type": "FeatureCollection", "features": []}
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        print(f"已创建新的 {filename} 文件")

    # 读取现有文件内容
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # 如果文件损坏或不存在，创建新的结构
        data = {"type": "FeatureCollection", "features": []}

    # 检查坐标是否已存在
    coordinates = [float(x), float(y)]
    for feature in data["features"]:
        if feature["geometry"]["coordinates"] == coordinates:
            print(f"坐标 ({x}, {y}) 已存在于 {filename} 文件中，跳过添加")
            return False

    # 生成ID（如果没有提供）
    if point_id is None:
        # 为新点分配正确的ID
        max_id = 0
        for feature in data["features"]:
            feature_id = feature.get("properties", {}).get("id", 0)
            if isinstance(feature_id, int):
                max_id = max(max_id, feature_id)
        point_id = max_id + 1

    # 创建点特征
    point_feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinates},
        "properties": {"id": point_id, "type": "break_point"},
    }

    # 添加新特征
    data["features"].append(point_feature)

    # 写回文件
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"已将坐标 ({x}, {y}) 添加到 {filename} 文件中，ID: {point_id}")
    return True


# 读取break_point.geojson文件并转换为行列坐标,找出其下游一个单位的点作为junction
def get_break_points(identified_streams, grid, fdir, flow_directions, break_point_geojson):
    break_points = set()
    set_point = set()
    set_points_with_id = {}  # 用于存储点坐标和对应的ID
    try:
        with open(break_point_geojson, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 首先找出ID最小的点（第一个添加的点）
        first_point_id = float("inf")
        for feature in data.get("features", []):
            if feature.get("geometry", {}).get("type") == "Point":
                point_id = feature.get("properties", {}).get("id", float("inf"))
                first_point_id = min(first_point_id, point_id)

        for feature in data.get("features", []):
            if feature.get("geometry", {}).get("type") == "Point":
                coords = feature["geometry"]["coordinates"]
                point_id = feature.get("properties", {}).get("id")

                # 排除第一个点（ID最小的点）
                # if point_id == first_point_id:
                #     continue

                # 将地理坐标转换为行列坐标
                x, y = coords[0], coords[1]
                _, _,row, col = snap_point_to_stream(x, y, identified_streams, grid)
                set_point.add((row, col))
                # 存储点坐标和对应的ID
                set_points_with_id[(row, col)] = point_id

                if identified_streams[row, col] == 1:
                    print(f"break point 在河道上")
                else:
                    print(f"break point 不在河道上")

                # 查找该点的最近下游点
                downstream_cell = find_downstream_cell(
                    row, col, fdir, identified_streams, flow_directions
                )
                if downstream_cell is not None:
                    break_points.add(downstream_cell)
                else:
                    print(f"找不到点({row}, {col})的下游点")
    except Exception as e:
        print(f"读取break_point.geojson文件时出错: {e}")
    return break_points, set_point, set_points_with_id


# 查找指定像元的下游邻居
def find_downstream_cell(row, col, fdir, identified_streams, flow_directions):
    # 获取当前像元的流向值
    direction = fdir[row, col]

    # 根据流向查找下游像元
    for dir_val, (d_row, d_col) in flow_directions.items():
        if dir_val == direction:
            downstream_row, downstream_col = row - d_row, col - d_col

            # 检查下游像元是否在有效范围内
            if (
                0 <= downstream_row < fdir.shape[0]
                and 0 <= downstream_col < fdir.shape[1]
            ):

                # 检查邻居像元是否在河道上
                if identified_streams[downstream_row, downstream_col] == 1:
                    return (downstream_row, downstream_col)
                else:
                    print(f"下游点({downstream_row}, {downstream_col})不在河道上")

    # 如果没有找到下游像元，返回None
    return None


# 查找指定像元的所有上游邻居
def find_upstream_cells(row, col, fdir, identified_streams, flow_directions):
    upstream_cells = []
    for direction, (d_row, d_col) in flow_directions.items():
        neighbor_row, neighbor_col = row + d_row, col + d_col

        # 检查邻居像元是否在有效范围内
        if 0 <= neighbor_row < fdir.shape[0] and 0 <= neighbor_col < fdir.shape[1]:
            # 检查邻居像元是否在河道上
            if identified_streams[neighbor_row, neighbor_col] == 1:
                # 检查邻居像元是否流向当前像元
                if fdir[neighbor_row, neighbor_col] == direction:
                    upstream_cells.append((neighbor_row, neighbor_col))
    return upstream_cells


# 创建并写入源头点特征的函数
def create_and_write_source_point(row, col, grid):
    """
    创建源头点特征并写入sources.geojson文件

    参数:
    row : int
        源头点的行坐标
    col : int
        源头点的列坐标
    """
    global source_count

    # 记录源头点到geojson文件
    source_count += 1

    # 将行列坐标转换为地理坐标
    geo_x, geo_y = View.affine_transform(grid.affine, col+0.5, row+0.5)

    # 创建源头点特征
    source_point = {"type": "Point", "coordinates": [float(geo_x), float(geo_y)]}

    source_feature = {
        "type": "Feature",
        "geometry": source_point,
        "properties": {
            "id": int(source_count),
            "row": int(row),
            "col": int(col),
            "type": "source",
        },
    }

    # 读取现有文件内容（如果存在）
    sources_data = {"type": "FeatureCollection", "features": []}
    try:
        with open("sources.geojson", "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            # 使用现有文件中的所有特征
            sources_data["features"] = existing_data["features"]
    except (FileNotFoundError, json.JSONDecodeError):
        # 如果文件不存在或损坏，使用空的特征列表
        pass

    # 添加新特征
    sources_data["features"].append(source_feature)

    # 写回文件
    try:
        with open("sources.geojson", "w", encoding="utf-8") as f:
            json.dump(sources_data, f, ensure_ascii=False)
        print(f"源头点 {source_count} 已写入sources.geojson文件")
    except Exception as e:
        print(f"写入sources.geojson文件时出错: {e}")


# 单独遍历河道找到源头点的函数
def find_and_record_sources(
    identified_streams, fdir, flow_directions, junction_count, grid
):
    """
    单独遍历河道网络找到所有源头点并记录

    参数:
    identified_streams : array
        河道网络数组
    fdir : array
        流向数组
    flow_directions : dict
        流向映射字典
    junction_count : int
        junction点计数

    """
    global source_count

    # 设置source_count的起点为junction_count+1
    source_count = junction_count

    # 创建一个记录已处理像元的数组
    processed = np.zeros_like(identified_streams, dtype=bool)

    # 遍历整个河道网络
    for row in range(identified_streams.shape[0]):
        for col in range(identified_streams.shape[1]):
            # 检查是否是河道像元且未处理过
            if identified_streams[row, col] == 1 and not processed[row, col]:
                # 标记为已处理
                processed[row, col] = True

                # 查找当前像元的所有上游邻居
                upstream_cells = find_upstream_cells(
                    row, col, fdir, identified_streams, flow_directions
                )

                # 如果没有上游邻居，则为源头点
                if len(upstream_cells) == 0:
                    create_and_write_source_point(row, col, grid)

    print(f"总共找到 {source_count - junction_count} 个源头点")


####  2.生成选择阈值并生成水系（Identified Streams）   ####
def calculate_identified_streams(
    acc, cell_size_x=30, cell_size_y=30, Area_Threshold=None, threshold_percentile=99.8
):
    """
    根据面积阈值或百分位数计算identified_streams和相关参数

    参数:
    acc : array
        流量累积数组
    cell_size_x : float
        经度方向上的像元大小，默认为30
    cell_size_y : float
        纬度方向上的像元大小，默认为30
    Area_Threshold : float, optional
        面积阈值（平方米），如果提供则根据此值反算threshold_value
    threshold_percentile : float
        百分位数，默认为99.8，仅在Area_Threshold为None时使用

    返回:
    dict : 包含identified_streams, threshold_value, Area_Threshold的字典
    """

    # 先去除0值，再计算百分位数
    acc_nonzero = acc[acc > 0]  # 获取非零值
    print(f"非零值总数: {len(acc_nonzero)}")
    print(f"非零值范围: {acc_nonzero.min()} - {acc_nonzero.max()}")
    print(f"阈值百分位数: {threshold_percentile}")
    if Area_Threshold is not None:
        # 模式1: 用户输入面积阈值，反算threshold_value
        # 计算单个像元代表的面积
        pixel_area = cell_size_x * cell_size_y

        # 根据面积阈值计算需要的像元数量
        required_pixels = Area_Threshold * 1000000 / pixel_area  # 转换为平方米
        # 根据像元数量计算threshold_value（使用正确的百分位数方法）
        if len(acc_nonzero) > 0:
            threshold_value = round(required_pixels)
            print(threshold_value)
        else:
            threshold_value = 1
            print("没有像元满足条件")

    else:
        # 模式2: 使用默认的百分位数计算threshold_value
        if len(acc_nonzero) > 0:
            threshold_value = np.percentile(acc_nonzero, threshold_percentile)
        else:
            threshold_value = 1

    # 创建 Identified Streams 图层
    identified_streams = np.zeros_like(acc, dtype=int)
    identified_streams[acc >= threshold_value] = 1

    # 统计identified_streams中值为1的像元个数
    stream_pixel_count = np.sum(identified_streams == 1)

    # 计算实际的面积阈值
    actual_area_threshold = threshold_value * (cell_size_x * cell_size_y) / 1000000

    print(f"河流网络像元个数: {stream_pixel_count}")
    print(
        f"流量累积阈值：{threshold_value}，面积阈值：{actual_area_threshold} 平方千米"
    )

    return {
        "identified_streams": identified_streams,
        "threshold_value": threshold_value,
        "Area_Threshold": actual_area_threshold,
        "stream_pixel_count": stream_pixel_count,
    }


####   3.生成子流域    ####
# 为break_point.geojson和upstream_cells.geojson中的所有点生成流域
def generate_catchments_for_all_points(grid, fdir, dirmap):
    """
    为break_point.geojson和upstream_cells.geojson中的所有点生成流域
    """
    import json

    # 存储所有需要生成流域的点
    all_points = []

    # 读取break_point.geojson中的点
    try:
        with open("break_point.geojson", "r", encoding="utf-8") as f:
            break_point_data = json.load(f)

        for feature in break_point_data["features"]:
            if feature["geometry"]["type"] == "Point":
                coords = feature["geometry"]["coordinates"]
                point_id = feature["properties"]["id"]
                # 只将'id'为1的点加入到all_points中
                if point_id == 1:
                    all_points.append(
                        {
                            "x": coords[0],
                            "y": coords[1],
                            "id": f"break_point_{point_id}",
                        }
                    )
    except Exception as e:
        print(f"读取break_point.geojson时出错: {e}")

    # 读取upstream_cells.geojson中的点
    try:
        with open("upstream_cells.geojson", "r", encoding="utf-8") as f:
            upstream_data = json.load(f)

        for feature in upstream_data["features"]:
            if feature["geometry"]["type"] == "Point":
                coords = feature["geometry"]["coordinates"]
                point_id = feature["properties"]["id"]
                all_points.append(
                    {"x": coords[0], "y": coords[1], "id": f"upstream_{point_id}"}
                )
    except Exception as e:
        print(f"读取upstream_cells.geojson时出错: {e}")

    # 为每个点生成流域
    catchments = {}
    for point in all_points:
        try:
            # 生成流域
            catch = grid.catchment(
                x=point["x"],
                y=point["y"],
                fdir=fdir,
                dirmap=dirmap,
                xytype="coordinate",
            )
            # 添加检查
            if np.sum(catch > 0) == 0:
                print(f"警告: 点 {point['id']} 生成的流域为空")
            # 保存流域数据
            catchments[point["id"]] = catch
            print(f"已为点 {point['id']} (x={point['x']}, y={point['y']}) 生成流域")

        except Exception as e:
            print(f"为点 {point['id']} 生成流域时出错: {e}")

    return catchments


# 流域相减
def compute_unique_areas(all_catchments):
    """
    按照流域编号倒序计算每个流域的独有区域

    算法逻辑：
    1. 按流域的编号倒序计算，因为下游流域肯定没有支流，就不用进行计算
    2. 比如说上游流域就减去下游流域
    3. 按顺序进行计算独有区域

    Parameters:
    all_catchments: dict
        包含所有流域栅格的字典，键为流域ID，值为Raster对象

    Returns:
    dict
        每个流域独有的区域
    """
    # 获取所有流域ID
    catchment_ids = list(all_catchments.keys())

    # 按照流域编号进行排序
    # 假设流域ID格式为数字-数字或数字-数字_new的形式
    def extract_sort_key(catchment_id):
        # 提取ID中的主编号和次编号用于排序
        import re

        # 匹配格式如 "break_point_1.1", "upstream_9-2", "8-1_new" 等
        match = re.search(r"(\d+)[\-\.](\d+)", catchment_id)
        if match:
            # 返回主编号和次编号的元组，用于排序
            return (int(match.group(1)), int(match.group(2)))
        else:
            # 如果没有匹配到特定格式，尝试提取第一个数字
            match = re.search(r"(\d+)", catchment_id)
            return (int(match.group(1)), 0) if match else (0, 0)

    # 按照编号倒序排列
    sorted_catchment_ids = sorted(catchment_ids, key=extract_sort_key, reverse=True)

    print("处理顺序:", sorted_catchment_ids)  # 用于调试，可以看到实际的处理顺序

    unique_areas = {}
    processed_areas = {}  # 存储已经处理过的流域独有区域

    # 按倒序处理每个流域
    for catchment_id in sorted_catchment_ids:
        current_catchment = all_catchments[catchment_id]

        # 初始化当前流域为全流域
        unique_area = np.where(current_catchment > 0, 1, 0).astype(np.uint8)

        # 减去所有已经处理过的下游流域区域
        for processed_id, processed_area in processed_areas.items():
            # 从当前流域中减去已处理流域的独有区域
            unique_area = np.where(
                (unique_area > 0) & (processed_area > 0),
                0,  # 重叠区域置为0
                unique_area,  # 非重叠区域保持不变
            )

        # 保存当前流域的独有区域
        unique_areas[catchment_id] = unique_area
        processed_areas[catchment_id] = unique_area

    return unique_areas


# 计算流域面积
def calculate_catchment_area(grid_data, cell_size_x=30, cell_size_y=30, unit="km2"):
    """
    计算流域面积（假设栅格大小为30*30米）

    参数:
    grid_data: 栅格数据（numpy数组），流域区域值应为1，其他区域为0或NaN
    unit: 面积单位，'m2' 表示平方米，'km2' 表示平方公里，'ha' 表示公顷

    返回:
    area: 流域面积
    """
    # 获取有效像元数量（非零像元）
    valid_cells = np.sum(grid_data > 0)

    # 单个像元面积（平方米）
    cell_area_m2 = cell_size_x * cell_size_y  # 30米 * 30米 = 900平方米

    # 计算总面积（平方米）
    total_area_m2 = valid_cells * cell_area_m2

    # 根据指定单位转换
    if unit == "km2":
        area = total_area_m2 / 1000000  # 转换为平方公里
    elif unit == "ha":
        area = total_area_m2 / 10000  # 转换为公顷
    elif unit == "m2":
        area = total_area_m2  # 保持平方米
    else:
        raise ValueError("单位必须是 'm2', 'km2', 或 'ha'")

    return area


# 获取流域中心点
def find_raster_centroid_fast(grid_data, grid):
    """
    快速计算栅格中心点

    参数:
    grid_data: 栅格数据（numpy数组）

    返回:
    centroid_row, centroid_col: 中心点的行列坐标
    """
    # 获取所有有效像元的坐标
    valid_rows, valid_cols = np.where(grid_data > 0)

    # 直接计算平均值（使用内置函数，效率最高）
    centroid_row = np.mean(valid_rows)
    centroid_col = np.mean(valid_cols)
    # 将行列坐标转换为地理坐标（经纬度）
    x, y = grid.affine * (centroid_col, centroid_row)

    return x, y


# 提取流域边界转为polygon
def create_polygon_from_raster(area_data, grid_obj, catchment_id):
    """
    使用rasterio从栅格数据创建多边形
    """
    # 确保数据是二值化的uint8类型
    area_data = np.where(area_data > 0, 1, 0).astype(np.uint8)

    # 创建临时GeoTIFF文件
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_file:
        temp_filename = tmp_file.name

    try:
        # 获取仿射变换矩阵
        if hasattr(grid_obj, "affine"):
            transform = grid_obj.affine
        elif hasattr(grid_obj, "viewfinder") and hasattr(grid_obj.viewfinder, "affine"):
            transform = grid_obj.viewfinder.affine
        else:
            # 创建默认的仿射变换矩阵
            transform = rasterio.transform.from_bounds(
                0,
                0,
                area_data.shape[1],
                area_data.shape[0],
                area_data.shape[1],
                area_data.shape[0],
            )

        # 使用rasterio创建GeoTIFF文件
        with rasterio.open(
            temp_filename,
            "w",
            driver="GTiff",
            height=area_data.shape[0],
            width=area_data.shape[1],
            count=1,
            dtype=np.uint8,
            transform=transform,
            crs="EPSG:4326",  # 设置坐标系，根据实际情况调整
        ) as dst:
            dst.write(area_data, 1)

        # 使用rasterio读取并处理
        with rasterio.open(temp_filename) as src:
            data = src.read(1)
            transform = src.transform

            # 创建mask，值大于0的像元为有效
            mask = data > 0

            # 生成形状，尝试不同的connectivity参数
            shapes_gen = features.shapes(
                data, mask=mask, transform=transform, connectivity=8
            )

            # 提取所有有效多边形
            polygons = []
            for geom, value in shapes_gen:
                if value > 0:
                    # 使用 shape 函数从GeoJSON字典创建多边形
                    shapely_poly = shape(geom)
                    polygons.append(shapely_poly)

            return polygons

    except Exception as e:
        print(f"创建多边形时出错: {e}")
        import traceback

        traceback.print_exc()
        return []
    finally:
        # 清理临时文件
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)


# 生成geojson文件
def save_all_catchments_to_single_geojson(
    unique_areas,
    grid_obj,
    cell_size_x=30,
    cell_size_y=30,
    filename="sub_catchment.geojson",
):
    """
    将所有子流域保存为一个GeoJSON文件，使用真实的DEM分辨率计算面积

    参数:
    unique_areas: 所有流域的栅格数据字典
    grid_obj: pysheds Grid对象
    filename: 输出文件名
    """
    with open("sub_catchment.geojson", "w", encoding="utf-8") as f:
        # 写入geojson文件头
        f.write('{"type": "FeatureCollection", "features": []}')

    all_features = []

    # 为每个流域创建GeoJSON特征
    for catchment_id, area_data in unique_areas.items():
        print(f"\n处理流域: {catchment_id}")
        print(f"  有效像元数: {np.sum(area_data > 0)}")
        print(f"  数据范围: {area_data.min()} 到 {area_data.max()}")
        print(f"  数据类型: {area_data.dtype}")
        print(f"  数据形状: {area_data.shape}")
        try:
            # 使用rasterio方法创建多边形
            polygons = create_polygon_from_raster(area_data, grid_obj, catchment_id)

            if not polygons:
                print(f"  警告: 未找到流域 {catchment_id} 的有效几何形状")
                print(
                    f"  area_data 摘要: 唯一值={np.unique(area_data)}, 总和={np.sum(area_data)}"
                )
                continue

            # 处理第一个多边形（通常也是唯一一个）
            polygon = polygons[0]
            # 计算有效像元数量(可用于验证面积)
            valid_cells = np.sum(area_data > 0)
            # 使用find_raster_centroid_fast函数计算中心点
            centroid_x, centroid_y = find_raster_centroid_fast(area_data, grid_obj)
            # 计算面积
            area_km2 = calculate_catchment_area(
                area_data, cell_size_x, cell_size_y, unit="km2"
            )

            # 获取外环坐标
            try:
                exterior_coords = list(polygon.exterior.coords)
                # 检查坐标数量
                if len(exterior_coords) < 4:
                    print(
                        f"  警告：流域 {catchment_id} 的多边形坐标点过少 ({len(exterior_coords)} 个点)"
                    )
                    # 对于极小的区域，可能需要特殊处理
                    if len(exterior_coords) < 3:
                        print(f"  跳过流域 {catchment_id}: 坐标点不足")
                        continue

                # 确保多边形闭合
                if exterior_coords[0] != exterior_coords[-1]:
                    exterior_coords.append(exterior_coords[0])
                    print(f"修复多边形闭合")

                # 验证坐标有效性
                valid_coords = True
                for i, coord in enumerate(exterior_coords):
                    if not (
                        isinstance(coord[0], (int, float))
                        and isinstance(coord[1], (int, float))
                    ):
                        print(f"  警告: 流域 {catchment_id} 包含无效坐标 {i}: {coord}")
                        valid_coords = False
                        break

                if not valid_coords:
                    continue

            except Exception as e:
                print(f"  处理外环坐标时出错: {e}")
                continue
            # 创建GeoJSON特征
            # 提取catchment_id中的数字部分（包括小数点）

            numeric_part = re.search(r"\d+(?:\.\d+)?", catchment_id)
            watershed_id = (
                "Watershed" + numeric_part.group()
                if numeric_part
                else "Watershed" + catchment_id
            )

            # 创建GeoJSON特征
            feature = {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [exterior_coords]},
                "properties": {
                    "id": watershed_id,
                    "area_km2": round(area_km2, 3),
                    "valid_cells": int(valid_cells),
                    "centroid_x": round(centroid_x, 6),
                    "centroid_y": round(centroid_y, 6),
                },
            }
            all_features.append(feature)

        except Exception as e:
            print(f"  处理流域 {catchment_id} 时出错: {e}")
            continue

    # 创建GeoJSON对象
    geojson_data = {"type": "FeatureCollection", "features": all_features}

    # 保存到文件
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    print(f"\n已保存所有子流域到GeoJSON文件: {filename}")
    print(f"总共保存了 {len(all_features)} 个流域要素")

    # 打印每个流域的摘要信息
    for feature in all_features:
        props = feature["properties"]
        print(
            f"  流域ID: {props['id']}, 面积: {props['area_km2']} km², "
            f"中心点: ({props['centroid_x']}, {props['centroid_y']})"
        )

    return filename


####   4.生成河道拓扑关系   ####
# 读取upstream_cells.geojson文件并构建upstream点之间的下游关系字典
def build_upstream_downstream_relationships(
    break_point_geojson,
    upstream_geojson,
    source_deleted_geojson,
    identified_streams,
    grid,
    fdir,
    flow_directions,
    file_name,
):
    """
    构建upstream点之间的下游关系 (upstream_id -> downstream_upstream_id)
    从每个upstream点开始，沿着河道网络向下游遍历，直到找到下一个upstream点
    同时也将break_point.geojson中的第一个点（id为1）加入检索队列
    同时也将source_deleted.geojson中的所有点加入检索队列

    参数:
    identified_streams : array
        河道网络数组
    grid : Grid
        Grid对象
    fdir : array
        流向数组
    flow_directions : dict
        流向映射字典
    find_downstream_cell : function
        查找下游像元的函数
    file_name : str
        dict的保存路径
    返回:
    dict : upstream点之间的下游关系字典
    """
    downstream_dict = {}

    try:
        # 读取upstream_cells.geojson文件
        with open(upstream_geojson, "r", encoding="utf-8") as f:
            upstream_data = json.load(f)

        # 读取break_point.geojson文件
        break_point_data = None
        try:
            with open(break_point_geojson, "r", encoding="utf-8") as f:
                break_point_data = json.load(f)
        except FileNotFoundError:
            print("未找到break_point.geojson文件")

        # 读取source_deleted.geojson文件
        source_deleted_data = None
        try:
            with open(source_deleted_geojson, "r", encoding="utf-8") as f:
                source_deleted_data = json.load(f)
        except FileNotFoundError:
            print("未找到source_deleted.geojson文件")

        # 创建一个位置索引 (row, col) -> upstream_id
        upstream_positions = {}
        for feature in upstream_data["features"]:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                upstream_id = props["id"]
                row = props["row"]
                col = props["col"]
                upstream_positions[(row, col)] = upstream_id

        # 如果存在break_point.geojson文件，将其中id为1的点也加入索引
        if break_point_data:
            for feature in break_point_data["features"]:
                if (
                    feature["geometry"]["type"] == "Point"
                    and feature["properties"].get("id") == 1
                ):
                    # 获取break point的地理坐标
                    coords = feature["geometry"]["coordinates"]
                    x, y = coords[0], coords[1]
                    # 将地理坐标转换为行列坐标
                    col, row = grid.nearest_cell(x, y)
                    # 使用特殊ID标识break point
                    upstream_positions[(row, col)] = "break_point_1"
                    print(f"添加break point (id=1)到位置: row={row}, col={col}")
                    break

        # 如果存在source_deleted.geojson文件，将其所有点加入索引
        if source_deleted_data:
            for feature in source_deleted_data["features"]:
                if feature["geometry"]["type"] == "Point":
                    props = feature["properties"]
                    source_deleted_id = props["id"]
                    row = props["row"]
                    col = props["col"]
                    upstream_positions[(row, col)] = source_deleted_id
                    print(
                        f"添加source deleted点 (id={source_deleted_id})到位置: row={row}, col={col}"
                    )

        # 为每个upstream点查找其下游的upstream点
        all_features_to_process = upstream_data["features"][:]
        # 如果有source_deleted数据，也添加到处理队列中
        if source_deleted_data:
            all_features_to_process.extend(source_deleted_data["features"])

        for feature in all_features_to_process:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                # 获取点的ID，对于source_deleted点，我们使用一个特殊的标识
                upstream_id = props["id"]

                start_row = props["row"]
                start_col = props["col"]
                # 从当前upstream点开始沿着河道向下游遍历
                current_row, current_col = start_row, start_col
                found_downstream = False
                visited_cells = set()  # 防止无限循环

                while not found_downstream:
                    # 标记当前单元格已访问
                    visited_cells.add((current_row, current_col))

                    # 查找当前点的下游点
                    downstream_cell = find_downstream_cell(
                        current_row,
                        current_col,
                        fdir,
                        identified_streams,
                        flow_directions,
                    )

                    # 如果没有下游点，说明到达了流域出口
                    if downstream_cell is None:
                        print(
                            f"upstream点 {upstream_id} 到达流域出口，没有下游upstream点"
                        )
                        break

                    next_row, next_col = downstream_cell

                    # 检查是否进入循环（防止无限循环）
                    if (next_row, next_col) in visited_cells:
                        print(f"upstream点 {upstream_id} 遇到循环，停止搜索")
                        break

                    # 检查下一个点是否是upstream点或break point或source deleted点
                    if (next_row, next_col) in upstream_positions:
                        downstream_upstream_id = upstream_positions[
                            (next_row, next_col)
                        ]
                        downstream_dict[upstream_id] = downstream_upstream_id
                        found_downstream = True
                        if downstream_upstream_id == "break_point_1":
                            print(
                                f"upstream点 {upstream_id} 找到下游break point (id=1)"
                            )
                        else:
                            print(
                                f"upstream点 {upstream_id} 找到下游upstream点 {downstream_upstream_id}"
                            )
                    else:
                        # 如果下一个点不是upstream点，但仍在河道上，继续遍历
                        if (
                            0 <= next_row < identified_streams.shape[0]
                            and 0 <= next_col < identified_streams.shape[1]
                            and identified_streams[next_row, next_col] == 1
                        ):
                            current_row, current_col = next_row, next_col
                        else:
                            # 离开河道，停止搜索
                            print(f"upstream点 {upstream_id} 离开河道，停止搜索")
                            break

                # 如果没有找到下游upstream点，可能是因为到达了流域出口
                if not found_downstream:
                    print(f"upstream点 {upstream_id} 未找到下游upstream点")

        print("\n成功构建upstream点之间的下游关系字典:")
        for upstream_id, downstream_id in downstream_dict.items():
            if downstream_id == "break_point_1":
                print(f"  {upstream_id} -> break_point_1")
            else:
                print(f"  {upstream_id} -> {downstream_id}")

    except FileNotFoundError as e:
        print(f"文件未找到: {e}")
    except Exception as e:
        print(f"构建upstream点之间下游关系时出错: {e}")

    # 确保字典中的所有键值都可以被JSON序列化
    serializable_dict = {}
    for key, value in downstream_dict.items():
        # 将numpy数据类型转换为Python原生类型
        if hasattr(key, "item"):
            serializable_key = key.item()
        else:
            serializable_key = key

        if hasattr(value, "item"):
            serializable_value = value.item()
        else:
            serializable_value = value

        serializable_dict[str(serializable_key)] = str(serializable_value)

    # 保存到JSON文件
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(serializable_dict, f, ensure_ascii=False, indent=2)
    print("成功将downstream_dict保存")

    return downstream_dict


####   5.生成河段LineString   ####
# 将 identified_streams 栅格数据转换为 GeoJSON LineString 格式
def identified_streams_to_linestring_geojson(
    sources_geojson,
    junctions_geojson,
    grid,
    fdir,
    flow_directions,
    identified_streams,
    output_path="identified_streams.geojson",
):
    """
    将 identified_streams 栅格数据转换为 GeoJSON LineString 格式（按照河网拓扑结构）
    每条河段从源头点(sources.geojson)到汇流点(junctions.geojson)

    参数:
    sources_geojson: str
        源头点geojson文件路径
    junctions_geojson: str
        汇流点geojson文件路径
    grid: Grid
        pysheds Grid对象
    fdir: array
        流向数组
    flow_directions: dict
        流向映射字典
    identified_streams: array
        河道网络栅格数组
    output_path: str
        输出GeoJSON文件路径
    """
    # 收集所有终点（junction）点
    junction_points = {}  # (row, col) -> point_id
    try:
        with open(junctions_geojson, "r", encoding="utf-8") as f:
            junctions_data = json.load(f)
        for feature in junctions_data["features"]:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                point_id = props["id"]
                row = props["row"]
                col = props["col"]
                junction_points[(row, col)] = f"junction_{point_id}"
    except Exception as e:
        print(f"读取junctions.geojson时出错: {e}")

    # 收集所有起点（source）点
    source_points = {}  # (row, col) -> source_id
    try:
        with open(sources_geojson, "r", encoding="utf-8") as f:
            sources_data = json.load(f)
        for feature in sources_data["features"]:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                source_id = props["id"]
                row = props["row"]
                col = props["col"]
                source_points[(row, col)] = source_id
    except Exception as e:
        print(f"读取sources.geojson时出错: {e}")

    print(f"总共找到 {len(source_points)} 个源头点和 {len(junction_points)} 个汇流点")

    # 创建用于存储LineString的geojson数据结构
    linestrings_data = {"type": "FeatureCollection", "features": []}

    # 遍历所有源头点作为起点
    for (start_row, start_col), start_id in source_points.items():
        # 检查起点是否在河道上
        if not (
            0 <= start_row < identified_streams.shape[0]
            and 0 <= start_col < identified_streams.shape[1]
            and identified_streams[start_row, start_col] == 1
        ):
            print(f"跳过不在河道上的源头点: {start_id} at ({start_row}, {start_col})")
            continue

        # 沿着河道向下游遍历直到找到汇流点或离开河道
        path = [(start_row, start_col)]  # 包含起点
        current_row, current_col = start_row, start_col

        while True:
            # 查找当前点的下游点
            downstream_cell = find_downstream_cell(
                current_row, current_col, fdir, identified_streams, flow_directions
            )

            if downstream_cell is None:
                # 没有下游点，到达流域出口
                print(f"从源头 {start_id} 到流域出口，包含 {len(path)} 个栅格")
                end_id = "outlet"
                break

            next_row, next_col = downstream_cell

            # 添加到路径中
            path.append((next_row, next_col))

            # 检查是否到达了汇流点
            if (next_row, next_col) in junction_points:
                end_id = junction_points[(next_row, next_col)]
                print(
                    f"从源头 {start_id} 到汇流点 {end_id} 找到路径，包含 {len(path)} 个栅格"
                )
                break
            else:
                # 检查下一个点是否在河道上
                if (
                    0 <= next_row < identified_streams.shape[0]
                    and 0 <= next_col < identified_streams.shape[1]
                    and identified_streams[next_row, next_col] == 1
                ):
                    current_row, current_col = next_row, next_col
                else:
                    # 离开河道
                    end_id = "off_channel"
                    print(f"从源头 {start_id} 离开河道，包含 {len(path)} 个栅格")
                    break

        # 如果路径有至少2个点，创建LineString
        if len(path) >= 2:
            # 将路径上的栅格中心转换为经纬度坐标
            coordinates = []
            for row, col in path:
                # 计算栅格中心的地理坐标
                geo_x, geo_y = View.affine_transform(grid.affine, col+0.5, row+0.5)
                coordinates.append([float(geo_x), float(geo_y)])

            # 创建LineString特征
            linestring_feature = {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "From_point": f"source_{start_id}",
                    "To_point": end_id,
                    "length": len(path),
                },
            }

            linestrings_data["features"].append(linestring_feature)
            print(f"创建河段: 从源头 {start_id} 到 {end_id}，长度 {len(path)}")

    # 保存到文件
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(linestrings_data, f, ensure_ascii=False)
        print(
            f"成功生成 {len(linestrings_data['features'])} 条河段LineString，保存到 {output_path}"
        )
    except Exception as e:
        print(f"保存{output_path}时出错: {e}")

    return linestrings_data


# 合并sources.geojson和junctions.geojson中所有的点，并生成河段LineString
def generate_river_network_linestrings(
    junctions_geojson,
    break_point_geojson,
    upstream_cells_geojson,
    river_network_linestrings,
    identified_streams,
    grid,
    fdir,
    flow_directions,
):
    """
    1. 合并sources.geojson、junctions.geojson和break_point.geojson中"id": 1的点
    2. 遍历所有输入点，以输入的点为起点，沿着河道（identified_streams）往下游进行遍历，直到找到另一个输入点为止
    3. 储存经历的所有栅格（包含起点和终点），将其中心转换成的经纬度坐标，储存为geojson的"LineString"文件

    参数:
    identified_streams : array
        河道网络数组
    grid : Grid
        Grid对象
    fdir : array
        流向数组
    flow_directions : dict
        流向映射字典
    """
    # 收集所有输入点
    input_points = {}  # (row, col) -> point_id

    # 读取junctions.geojson
    try:
        with open(junctions_geojson, "r", encoding="utf-8") as f:
            junctions_data = json.load(f)
        for feature in junctions_data["features"]:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                point_id = props["id"]
                row = props["row"]
                col = props["col"]
                input_points[(row, col)] = f"junction_{point_id}"
    except Exception as e:
        print(f"读取junctions.geojson时出错: {e}")

    # 读取break_point.geojson中id为1的点
    break_point_1_exists = False
    break_point_1_coords = None
    try:
        with open(break_point_geojson, "r", encoding="utf-8") as f:
            break_point_data = json.load(f)

        for feature in break_point_data["features"]:
            if feature["geometry"]["type"] == "Point":
                point_id = feature["properties"].get("id")
                coords = feature["geometry"]["coordinates"]
                x, y = coords[0], coords[1]
                col, row = grid.nearest_cell(x, y)

                # 特殊处理id为1的点
                if point_id == 1:
                    input_points[(row, col)] = "break_point_1"
                    break_point_1_coords = (row, col)
                    break_point_1_exists = True
                    print(f"添加break point (id=1)到位置: row={row}, col={col}")
                # else:
                #     # 将除id=1以外的所有点添加到input_points中
                #     input_points[(row, col)] = f"break_point_{point_id}"
                #     print(f"添加break point (id={point_id})到位置: row={row}, col={col}")

    except Exception as e:
        print(f"读取break_point.geojson时出错: {e}")

    # 读取upstream_cells.geojson中的点数据
    upstream_points = {}  # (row, col) -> upstream_id
    try:
        with open(upstream_cells_geojson, "r", encoding="utf-8") as f:
            upstream_data = json.load(f)
        for feature in upstream_data["features"]:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                upstream_id = props["id"]
                row = props["row"]
                col = props["col"]
                upstream_points[(row, col)] = upstream_id
    except Exception as e:
        print(f"读取upstream_cells.geojson时出错: {e}")

    print(f"总共找到 {len(input_points)} 个输入点")

    # 创建用于存储LineString的geojson数据结构
    linestrings_data = {"type": "FeatureCollection", "features": []}

    # 遍历所有输入点作为起点
    for (start_row, start_col), start_id in input_points.items():
        # 检查起点是否在河道上
        if not (
            0 <= start_row < identified_streams.shape[0]
            and 0 <= start_col < identified_streams.shape[1]
            and identified_streams[start_row, start_col] == 1
        ):
            print(f"跳过不在河道上的点: {start_id} at ({start_row}, {start_col})")
            continue

        # 沿着河道向下游遍历直到找到另一个输入点
        path = [(start_row, start_col)]  # 包含起点
        current_row, current_col = start_row, start_col

        while True:
            # 查找当前点的下游点
            downstream_cell = find_downstream_cell(
                current_row, current_col, fdir, identified_streams, flow_directions
            )

            if downstream_cell is None:
                # 没有下游点，到达流域出口
                print(f"从 {start_id} 到流域出口，包含 {len(path)} 个栅格")
                end_id = "outlet"
                break

            next_row, next_col = downstream_cell

            # 添加到路径中
            path.append((next_row, next_col))

            # 检查是否到达了另一个输入点
            if (next_row, next_col) in input_points:
                end_id = input_points[(next_row, next_col)]
                print(f"从 {start_id} 到 {end_id} 找到路径，包含 {len(path)} 个栅格")
                break
            else:
                # 检查下一个点是否在河道上
                if (
                    0 <= next_row < identified_streams.shape[0]
                    and 0 <= next_col < identified_streams.shape[1]
                    and identified_streams[next_row, next_col] == 1
                ):
                    current_row, current_col = next_row, next_col
                else:
                    # 离开河道
                    end_id = "off_channel"
                    print(f"从 {start_id} 离开河道，包含 {len(path)} 个栅格")
                    break

        # 如果路径有至少1个点，创建LineString
        if len(path) > 2:
            # 将路径上的栅格中心转换为经纬度坐标
            coordinates = []
            for row, col in path:
                # 计算栅格中心的地理坐标
                geo_x, geo_y = View.affine_transform(grid.affine, col+0.5, row+0.5)
                coordinates.append([float(geo_x), float(geo_y)])

            # 修改后的Riv-ID分配逻辑：
            # 1. 检查路径中是否有upstream点
            upstream_point_found = None
            break_point_1_in_path = False
            for row, col in path:
                if (row, col) in upstream_points:
                    upstream_point_found = upstream_points[(row, col)]
                # 检查路径中是否包含break_point_1_coords
                if break_point_1_exists and (row, col) == break_point_1_coords:
                    break_point_1_in_path = True

            # 2. 根据新规则分配Riv-ID
            if upstream_point_found:
                # 如果路径中有upstream点
                if break_point_1_in_path:
                    # 且路径中包含break_point.geojson中"id":1的点，则Riv-ID=break_1
                    riv_id = "1"
                else:
                    # 仅有点对应上upstream_cells.geojson中的一个点，则Riv-ID=这个点对应的id
                    riv_id = upstream_point_found
            else:
                # 若无upstream点，则Riv-ID=break_1
                riv_id = "1"

            # 创建LineString特征
            linestring_feature = {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "From_point": start_id,
                    "To_point": end_id,
                    "length": len(path),
                    "Riv-ID": riv_id,
                },
            }

            linestrings_data["features"].append(linestring_feature)
            print(
                f"创建河段: 从 {start_id} 到 {end_id}，长度 {len(path)}, Riv-ID: {riv_id}"
            )

    # 保存到文件
    try:
        with open(river_network_linestrings, "w", encoding="utf-8") as f:
            json.dump(linestrings_data, f, ensure_ascii=False)
        print(
            f"成功生成 {len(linestrings_data['features'])} 条河段LineString，保存到 river_network_linestrings.geojson"
        )
    except Exception as e:
        print(f"保存river_network_linestrings.geojson时出错: {e}")


# 计算并添加河流长度属性
def calculate_river_length(coordinates):
    """
    计算河流线段的总长度（单位：米）

    参数:
    coordinates: 坐标点列表，每个点为 [longitude, latitude] 格式

    返回:
    float: 河流长度（米）
    """
    total_length = 0.0

    # 遍历相邻的坐标点对，计算距离并累加
    for i in range(len(coordinates) - 1):
        point1 = (coordinates[i][1], coordinates[i][0])  # (lat, lon)
        point2 = (coordinates[i + 1][1], coordinates[i + 1][0])  # (lat, lon)
        segment_length = geodesic(point1, point2).meters
        total_length += segment_length

    return total_length


def add_river_length_to_geojson(file_path):
    """
    读取GeoJSON文件，计算每条河流的长度并添加到属性中

    参数:
    file_path: GeoJSON文件路径
    """
    # 读取GeoJSON文件
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 遍历所有特征，计算并添加长度属性
    for feature in data["features"]:
        if feature["geometry"]["type"] == "LineString":
            coordinates = feature["geometry"]["coordinates"]
            length = calculate_river_length(coordinates)
            # 将长度（米）添加到属性中
            feature["properties"]["length_meters"] = round(length, 2)
            # 也可以添加以公里为单位的长度
            feature["properties"]["length_km"] = round(length / 1000, 2)

    # 将更新后的数据写回到原文件中
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("河流长度计算完成，结果已保存到 river_network_linestrings.geojson")
    """
    读取GeoJSON文件，计算每条河流的长度并添加到属性中

    参数:
    file_path: GeoJSON文件路径
    """
    # 读取GeoJSON文件
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 遍历所有特征，计算并添加长度属性
    for feature in data["features"]:
        if feature["geometry"]["type"] == "LineString":
            coordinates = feature["geometry"]["coordinates"]
            length = calculate_river_length(coordinates)
            # 将长度（米）添加到属性中
            feature["properties"]["length_meters"] = round(length, 2)
            # 也可以添加以公里为单位的长度
            feature["properties"]["length_km"] = round(length / 1000, 2)

    # 将更新后的数据写回到原文件中
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("河流长度计算完成，结果已保存到 river_network_linestrings.geojson")


# 提取ID中的数字部分
def extract_watershed_number(prefix, watershed_id):
    """
    从流域ID中提取数字部分

    参数:
    prefix: str, 流域ID的前缀（如'Watershed'）
    watershed_id: str, 完整的流域ID（如'Watershed10.1'）

    返回:
    str: 提取的数字部分（如'10.1'）
    """
    if prefix in watershed_id:
        number_part = watershed_id.split(prefix)[1]
    else:
        number_part = watershed_id
    return number_part


####   8.根据river_network_linestrings_merge.geojson生成河段首尾坐标   ####
def extract_river_network_info(river_network_linestrings, dem, junctions_geojson, grid):
    """
    从river_network_linestrings_merge.geojson中提取河段信息，并关联起点和终点坐标及高程

    参数:
    merged_polygons: 合并后的多边形对象，用于判断使用哪个junction文件

    返回:
    dict: 包含河段信息的字典
    """

    # 确定使用哪个junction文件
    junction_file = junctions_geojson

    # 读取river_network_linestrings_merge.geojson文件
    try:
        with open(river_network_linestrings, "r", encoding="utf-8") as f:
            river_data = json.load(f)
    except Exception as e:
        print(f"读取{river_network_linestrings}文件时出错: {e}")
        return {}

    # 读取junction文件
    try:
        with open(junction_file, "r", encoding="utf-8") as f:
            junction_data = json.load(f)
    except Exception as e:
        print(f"读取{junction_file}文件时出错: {e}")
        return {}

    # 读取break_point.geojson文件
    try:
        with open("break_point.geojson", "r", encoding="utf-8") as f:
            break_point_data = json.load(f)
    except Exception as e:
        print(f"读取break_point.geojson文件时出错: {e}")
        return {}

    # 创建junction坐标字典 {id: coordinates}
    junction_coords = {}
    for feature in junction_data.get("features", []):
        if feature["geometry"]["type"] == "Point":
            props = feature["properties"]
            junction_id = props.get("id")
            coords = feature["geometry"]["coordinates"]
            junction_coords[f"junction_{junction_id}"] = coords

    # 创建break_point坐标字典 {id: coordinates}
    break_point_coords = {}
    for feature in break_point_data.get("features", []):
        if feature["geometry"]["type"] == "Point":
            props = feature["properties"]
            break_point_id = props.get("id")
            coords = feature["geometry"]["coordinates"]
            break_point_coords[f"break_point_{break_point_id}"] = coords

    # 构建结果字典
    result = {}

    # 遍历河段特征
    for feature in river_data.get("features", []):
        props = feature["properties"]
        riv_id = str(props.get("Riv-ID", ""))

        if riv_id:  # 确保riv_id不为空
            # 获取长度
            length_km = props.get("length_km", 0)

            # 获取起点和终点标识
            from_point = props.get("From_point", "")
            to_point = props.get("To_point", "")

            # 查找起点和终点坐标
            from_coords = None
            if from_point.startswith("junction_"):
                from_coords = junction_coords.get(from_point)
            elif from_point.startswith("break_point_"):
                from_coords = break_point_coords.get(from_point)

            to_coords = None
            if to_point.startswith("junction_"):
                to_coords = junction_coords.get(to_point)
            elif to_point.startswith("break_point_"):
                to_coords = break_point_coords.get(to_point)

            # 如果找到了起点和终点坐标，则添加到结果中
            if from_coords is not None and to_coords is not None:
                # 获取起点和终点的高程
                from_elevation = None
                to_elevation = None

                try:
                    # 使用 grid.nearest_cell 获取行列坐标，然后从 grid.view(dem) 中提取高程
                    from_col, from_row = grid.nearest_cell(
                        from_coords[0], from_coords[1]
                    )
                    to_col, to_row = grid.nearest_cell(to_coords[0], to_coords[1])

                    # 使用 grid.view(dem) 确保与 grid 的仿射变换参数一致
                    dem_view = grid.view(dem)
                    from_elevation = float(dem_view[from_row, from_col])
                    to_elevation = float(dem_view[to_row, to_col])
                except Exception as e:
                    print(f"获取点高程时出错: {e}")
                    from_elevation = None
                    to_elevation = None

                # 改进：创建包含点名称和坐标的字典结构
                from_point_info = {from_point: from_coords}
                to_point_info = {to_point: to_coords}

                result[riv_id] = {
                    "length_km": length_km,
                    "From_point": from_point_info,
                    "To_point": to_point_info,
                    "Elevation_of_FromPoint": from_elevation,
                    "Elevation_of_ToPoint": to_elevation,
                }
            elif from_coords is None:
                print(f"未找到起点 {from_point} 的坐标")
            elif to_coords is None:
                print(f"未找到终点 {to_point} 的坐标")

    return result


####   9.河段马斯京根参数  ####
# 从river_network_linestrings.geojson文件中初始化河流k和x参数字典
def initialize_river_kx_parameters(
    geojson_file_path="river_network_linestrings.geojson",
):
    """
    从river_network_linestrings.geojson文件中初始化河流k和x参数字典

    参数:
    geojson_file_path: str, river_network_linestrings.geojson文件路径

    返回:
    dict: 初始化后的河流k和x参数字典
    """
    global river_kx_parameters

    try:
        # 读取GeoJSON文件
        with open(geojson_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 遍历所有河段特征，提取Riv-ID并初始化k和x参数
        for feature in data["features"]:
            if feature["geometry"]["type"] == "LineString":
                riv_id = str(feature["properties"].get("Riv-ID", ""))
                if riv_id:
                    # 初始化每个河流ID的k和x值为None或默认值
                    river_kx_parameters[riv_id] = {"k": None, "x": None}

        print(f"成功初始化 {len(river_kx_parameters)} 条河流的k和x参数字典")
        return river_kx_parameters

    except FileNotFoundError:
        print(f"未找到文件: {geojson_file_path}")
        return {}
    except Exception as e:
        print(f"初始化河流k和x参数字典时出错: {e}")
        return {}


# 为指定的河流ID设置k和x参数值
def set_river_kx_parameter(river_id, k_value=None, x_value=None):
    """
    为指定的河流ID设置k和x参数值

    参数:
    river_id: str, 河流ID (如 "1.1", "1.2" 等)
    k_value: float, 河流的k参数值
    x_value: float, 河流的x参数值

    返回:
    bool: 操作是否成功
    """
    global river_kx_parameters

    # 检查河流ID是否存在
    if river_id not in river_kx_parameters:
        print(f"警告: 河流ID '{river_id}' 不存在于字典中，将自动创建")
        river_kx_parameters[river_id] = {"k": None, "x": None}

    # 设置k和x值
    if k_value is not None:
        river_kx_parameters[river_id]["k"] = k_value

    if x_value is not None:
        river_kx_parameters[river_id]["x"] = x_value

    print(f"已为河流 '{river_id}' 设置参数: k={k_value}, x={x_value}")
    return True


####   10.清除项目  ####
def delete_geojson_files(mode="all"):
    """
    删除工作目录下生成的geojson文件

    参数:
    mode: str, 删除模式
        - 'all': 删除所有geojson文件（原函数功能）
        - 'merge': 仅删除合并后的geojson文件（新增功能）
    """
    if mode == "all":
        # 原函数功能：删除所有geojson文件
        # 定义需要删除的geojson文件模式
        geojson_patterns = [
            "*.geojson",  # 所有geojson文件
        ]

        # 定义明确要删除的文件名（根据代码中出现的文件名）
        specific_files = [
            "sub_catchment.geojson",
            "sub_catchment_merge.geojson",
            "upstream_cells.geojson",
            "upstream_cells_merge.geojson",
            "junctions.geojson",
            "junctions_merge.geojson",
            "break_point.geojson",
            "source_delete.geojson",
            "river_network_linestrings.geojson",
            "river_network_linestrings_merge.geojson",
            "downstream_dict.json",
        ]

        deleted_files = []

        # 方法1: 删除特定文件
        for file_name in specific_files:
            if os.path.exists(file_name):
                try:
                    os.remove(file_name)
                    deleted_files.append(file_name)
                    print(f"已删除文件: {file_name}")
                except Exception as e:
                    print(f"删除文件 {file_name} 失败: {e}")

        # 方法2: 删除匹配模式的文件
        for pattern in geojson_patterns:
            for file_path in glob.glob(pattern):
                # 避免重复删除
                if file_path not in deleted_files and os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        deleted_files.append(file_path)
                        print(f"已删除文件: {file_path}")
                    except Exception as e:
                        print(f"删除文件 {file_path} 失败: {e}")

        print(f"总共删除了 {len(deleted_files)} 个geojson文件")
        if deleted_files:
            print("删除的文件列表:")
            for file in deleted_files:
                print(f"  - {file}")

    elif mode == "merge":
        # 新功能：仅删除合并后的geojson文件
        merge_files = [
            "sub_catchment_merge.geojson",
            "upstream_cells_merge.geojson",
            "junctions_merge.geojson",
            "river_network_linestrings_merge.geojson",
            "source_deleted.geojson",
            "downstream_dict_merge.json",
        ]

        deleted_files = []

        for file_name in merge_files:
            if os.path.exists(file_name):
                try:
                    os.remove(file_name)
                    deleted_files.append(file_name)
                    print(f"已删除合并文件: {file_name}")
                except Exception as e:
                    print(f"删除合并文件 {file_name} 失败: {e}")

        print(f"总共删除了 {len(deleted_files)} 个合并后的geojson文件")
        if deleted_files:
            print("删除的合并文件列表:")
            for file in deleted_files:
                print(f"  - {file}")

    else:
        print(f"无效的模式: {mode}。请使用 'all' 或 'merge'")


####   11.主程序  ####
# ------------------------------------------------------- 初始化流域 -------------------------------------------------------------
# 返回一个默认acc值
def get_default_acc_value(
    shapefile_path,
    dem_filename,
    tif_path,
    s_geojson=None,  # 张传鑫流域特征提取，传的流域边界的geojson数组
    threshold_percentile=50,
    cell_size_x=30,
    cell_size_y=30,
    dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
):

    # 如果提供了s_geojson参数，将其转换为临时GeoJSON文件
    if s_geojson is not None:
        # 创建临时GeoJSON文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8"
        ) as temp_file:
            json.dump(s_geojson, temp_file, ensure_ascii=False)
            temp_geojson_path = temp_file.name

        # 使用临时GeoJSON文件
        shapefile = gpd.read_file(temp_geojson_path)

    else:
        # 如果没有提供s_geojson，使用原有的shapefile_path
        if shapefile_path is None:
            raise ValueError("必须提供basin_file_path或s_geojson参数")

        shapefile = gpd.read_file(shapefile_path)

    # 计算shapefile的边界框
    bounds = shapefile.total_bounds
    minx, miny, maxx, maxy = bounds

    # 创建一个矩形缓冲区（可以根据需要调整）
    buffer_distance = 0  # 1000米缓冲区，可以根据实际需求调整
    buffered_bounds = [
        minx - buffer_distance,
        miny - buffer_distance,
        maxx + buffer_distance,
        maxy + buffer_distance,
    ]

    # 创建矩形几何对象
    from shapely.geometry import box

    buffered_shapefile = gpd.GeoDataFrame(
        [1], geometry=[box(*buffered_bounds)], crs=shapefile.crs
    )

    # 确保投影一致
    with rasterio.open(dem_filename) as src:
        # 将shapefile转换为与DEM相同的CRS
        buffered_shapefile = buffered_shapefile.to_crs(src.crs)

        # 获取几何边界
        geoms = [mapping(geom) for geom in buffered_shapefile.geometry]

        # 裁剪填洼后的DEM
        out_image, out_transform = mask(src, geoms, crop=True, nodata=np.nan)
        out_meta = src.meta.copy()

        # 更新元数据
        out_meta.update(
            {
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "nodata": np.nan,
            }
        )

        # 保存裁剪后的DEM到临时文件
        clipped_dem_path = "temp_clipped_dem.tif"
        with rasterio.open(clipped_dem_path, "w", **out_meta) as dest:
            dest.write(out_image)

    # 使用裁剪后的DEM重新创建Grid对象
    grid = Grid.from_raster(clipped_dem_path)
    dem = grid.read_raster(clipped_dem_path, data_name="dem")

    # 填充洼地
    pit_filled_dem = grid.fill_pits(dem)
    # 填充凹陷区域
    flooded_dem = grid.fill_depressions(pit_filled_dem)
    # 解决平面区域
    inflated_dem = grid.resolve_flats(flooded_dem)

    temp_filled_dem_path = tif_path
    print(tif_path)
    grid.to_raster(inflated_dem, temp_filled_dem_path)

    fdir = grid.flowdir(inflated_dem, dirmap=dirmap)
    acc = grid.accumulation(fdir=fdir, dirmap=dirmap, out_name="acc")

    # 先去除0值，再计算百分位数
    acc_nonzero = acc[acc > 0]  # 获取非零值

    print(f"非零值总数: {len(acc_nonzero)}")
    print(f"非零值范围: {acc_nonzero.min()} - {acc_nonzero.max()}")
    print(f"阈值百分位数: {threshold_percentile}")

    # 模式2: 使用默认的百分位数计算threshold_value
    if len(acc_nonzero) > 0:
        threshold_value = np.percentile(acc_nonzero, threshold_percentile)
    else:
        threshold_value = 1

    # 计算实际的面积阈值
    actual_area_threshold = threshold_value * (cell_size_x * cell_size_y) / 1000000

    print(
        f"流量累积阈值：{threshold_value}，面积阈值：{actual_area_threshold} 平方千米"
    )
    os.remove(clipped_dem_path)
    return actual_area_threshold


# 使用rasterio方法生成流域边界GeoJSON文件
def generate_watershed_boundary_with_rasterio(
    grid, catch, buffered_boundary_ori_geojson
):
    """
    使用rasterio方法生成流域边界GeoJSON文件

    参数:
    grid: Grid对象
    catch: 流域栅格数据
    buffered_boundary_ori_geojson: 输出的GeoJSON文件路径
    """
    import tempfile
    import rasterio
    from rasterio import features
    from shapely.geometry import shape, mapping
    import numpy as np
    import json
    from shapely.ops import unary_union

    # 确保catch数据是正确的整数类型
    catch_int = grid.view(catch).astype(np.int32)

    # 创建临时GeoTIFF文件用于rasterio处理
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_file:
        temp_filename = tmp_file.name

    try:
        # 获取仿射变换矩阵
        if hasattr(grid, "affine"):
            transform = grid.affine
        elif hasattr(grid, "viewfinder") and hasattr(grid.viewfinder, "affine"):
            transform = grid.viewfinder.affine
        else:
            # 创建默认的仿射变换矩阵
            transform = rasterio.transform.from_bounds(
                0,
                0,
                catch_int.shape[1],
                catch_int.shape[0],
                catch_int.shape[1],
                catch_int.shape[0],
            )

        # 使用rasterio创建GeoTIFF文件
        with rasterio.open(
            temp_filename,
            "w",
            driver="GTiff",
            height=catch_int.shape[0],
            width=catch_int.shape[1],
            count=1,
            dtype=np.int32,
            transform=transform,
            crs="EPSG:4326",  # 设置坐标系，根据实际情况调整
        ) as dst:
            dst.write(catch_int, 1)

        # 使用rasterio读取并处理
        with rasterio.open(temp_filename) as src:
            data = src.read(1)
            transform = src.transform

            # 创建mask，值大于0的像元为有效
            mask = data > 0

            # 生成形状，使用connectivity=8来连接8邻域
            shapes_gen = features.shapes(
                data, mask=mask, transform=transform, connectivity=8
            )

            # 提取所有有效多边形
            features_list = []
            geometries = []

            for i, (geom, value) in enumerate(shapes_gen):
                if value > 0:  # 只处理值大于0的区域
                    # 使用 shape 函数从GeoJSON字典创建多边形
                    shapely_poly = shape(geom)
                    geometries.append(shapely_poly)

            # 如果有多个几何体，合并它们
            if geometries:
                if len(geometries) > 1:
                    merged_geometry = unary_union(geometries)
                else:
                    merged_geometry = geometries[0]

                # 创建 GeoJSON 特征
                feature = {
                    "type": "Feature",
                    "geometry": mapping(merged_geometry),
                    "properties": {"id": 0, "value": 1, "name": "Catchment"},
                }
                features_list.append(feature)

        # 创建完整的 GeoJSON 对象
        geojson_obj = {"type": "FeatureCollection", "features": features_list}

        # 保存为 GeoJSON 文件
        with open(buffered_boundary_ori_geojson, "w", encoding="utf-8") as f:
            json.dump(geojson_obj, f, ensure_ascii=False, indent=2)

    finally:
        # 清理临时文件
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)


# 根据面积阈值或百分位数提取河流网络
def extract_river_network_with_threshold(
    acc,
    grid,
    fdir,
    Area_Threshold=None,
    cell_size_x=30,
    cell_size_y=30,
    threshold_percentile=99.8,
    dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
):
    """
    根据面积阈值或百分位数提取河流网络

    参数:
    acc : array
        流量累积数组
    Area_Threshold : float, optional
        面积阈值（平方千米），如果提供则根据此值反算threshold_value
    cell_size_x : float
        经度方向上的像元大小，默认为30
    cell_size_y : float
        纬度方向上的像元大小，默认为30
    threshold_percentile : float
        百分位数，默认为99.8，仅在Area_Threshold为None时使用

    返回:
    dict : 包含提取的河流网络和相关参数的字典
    """
    # 先去除0值，再计算百分位数
    acc_nonzero = acc[acc > 0]  # 获取非零值


    if Area_Threshold is not None:
        # 模式1: 用户输入面积阈值，反算threshold_value
        # 计算单个像元代表的面积
        pixel_area = cell_size_x * cell_size_y

        # 根据面积阈值计算需要的像元数量
        required_pixels = Area_Threshold * 1000000 / pixel_area  # 转换为平方米
        # 根据像元数量计算threshold_value（使用正确的百分位数方法）
        if len(acc_nonzero) > 0:
            threshold_value = round(required_pixels)
            print(threshold_value)
        else:
            threshold_value = 1
            print("没有像元满足条件")

    else:
        # 模式2: 使用默认的百分位数计算threshold_value
        if len(acc_nonzero) > 0:
            threshold_value = np.percentile(acc_nonzero, threshold_percentile)
        else:
            threshold_value = 1

    # 创建 Identified Streams 图层
    branches = grid.extract_river_network(fdir, acc > threshold_value, dirmap=dirmap)

    # 计算实际的面积阈值
    actual_area_threshold = threshold_value * (cell_size_x * cell_size_y) / 1000000

    print(
        f"流量累积阈值：{threshold_value}，面积阈值：{actual_area_threshold} 平方千米"
    )

    return {
        "identified_streams": branches,
        "threshold_value": threshold_value,
        "Area_Threshold": actual_area_threshold,
    }


# 将 pysheds 提取的河流网络转换为 GeoJSON 格式
def convert_branches_to_geojson(branches, output_file=None):
    """
    将 pysheds 提取的河流网络转换为 GeoJSON 格式

    参数:
    branches: pysheds extract_river_network 返回的结果
    output_file: 可选，输出的 GeoJSON 文件路径

    返回:
    geojson_data: 包含河流网络的 GeoJSON 对象
    """
    import json

    # 创建 GeoJSON 结构
    geojson_data = {"type": "FeatureCollection", "features": []}

    # 遍历每个分支并转换为 LineString 特征
    for i, feature in enumerate(branches["features"]):
        # 构建单个特征
        new_feature = {
            "type": "Feature",
            "properties": {"id": i, **feature.get("properties", {})},  # 包含原有的属性
            "geometry": {
                "type": "LineString",
                "coordinates": feature["geometry"]["coordinates"],
            },
        }
        geojson_data["features"].append(new_feature)

    # 如果指定了输出文件，则保存到文件
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        print(f"GeoJSON 文件已保存至: {output_file}")

    return geojson_data


# 生成初始流域边界和河道
def generate_initial_boundary_and_river(
    dem_filename,
    buffered_boundary_ori_geojson,
    identified_streams_geojson,
    tif_path,
    x=None,
    y=None,
    shapefile_path=None,
    Area_Threshold=None,
    dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
):
    # ================================================
    # 先裁剪矩形边框再重新生成流域边界
    # ================================================
    # 如果提供了shapefile，则先对完整DEM进行填洼，然后再裁剪
    # 读取完整DEM并进行填洼处理

    # # 读取shapefile
    # shapefile = gpd.read_file(shapefile_path)
    #
    # # 计算shapefile的边界框
    # bounds = shapefile.total_bounds
    # minx, miny, maxx, maxy = bounds
    #
    # # 创建一个矩形缓冲区（可以根据需要调整）
    # buffer_distance = 0  # 1000米缓冲区，可以根据实际需求调整
    # buffered_bounds = [
    #     minx - buffer_distance,
    #     miny - buffer_distance,
    #     maxx + buffer_distance,
    #     maxy + buffer_distance
    # ]
    #
    # # 创建矩形几何对象
    # buffered_shapefile = gpd.GeoDataFrame([1], geometry=[box(*buffered_bounds)], crs=shapefile.crs)
    #
    # # 确保投影一致
    # with rasterio.open(dem_filename) as src:
    #     # 将shapefile转换为与DEM相同的CRS
    #     buffered_shapefile = buffered_shapefile.to_crs(src.crs)
    #
    #     # 获取几何边界
    #     geoms = [mapping(geom) for geom in buffered_shapefile.geometry]
    #
    #     # 裁剪填洼后的DEM
    #     out_image, out_transform = mask(src, geoms, crop=True, nodata=np.nan)
    #     out_meta = src.meta.copy()
    #
    #     # 更新元数据
    #     out_meta.update({
    #         "driver": "GTiff",
    #         "height": out_image.shape[1],
    #         "width": out_image.shape[2],
    #         "transform": out_transform,
    #         "nodata": np.nan
    #     })
    #
    #     # 保存裁剪后的DEM到临时文件
    #     clipped_dem_path = "temp_clipped_dem.tif"
    #     with rasterio.open(clipped_dem_path, "w", **out_meta) as dest:
    #         dest.write(out_image)
    # clipped_dem_path = "temp_clipped_dem.tif"
    # # 使用裁剪后的DEM重新创建Grid对象
    # grid = Grid.from_raster(clipped_dem_path)
    # dem = grid.read_raster(clipped_dem_path, data_name='dem')
    #
    # # 填充洼地
    # pit_filled_dem = grid.fill_pits(dem)
    # # 填充凹陷区域
    # flooded_dem = grid.fill_depressions(pit_filled_dem)
    # # 解决平面区域
    # inflated_dem = grid.resolve_flats(flooded_dem)
    # 使用裁剪后的DEM重新创建Grid对象20260112
    grid = Grid.from_raster(tif_path)
    inflated_dem = grid.read_raster(tif_path, data_name="dem")

    ### D8方法计算流向 ###
    fdir = grid.flowdir(inflated_dem, dirmap=dirmap)

    ### 计算汇流累积量 (Flow Accumulation) ###

    acc = grid.accumulation(fdir=fdir, dirmap=dirmap, out_name="acc")
    # 自动选择流量累积最大值点作为倾泻点
    if "x" in locals() and "y" in locals() and x is not None and y is not None:
        # # 将x和y坐标组合成数组
        # xy = np.column_stack([x, y])
        # new_xy = grid.snap_to_mask(acc > 5, xy, return_dist=False)
        # # 提取捕捉后的新坐标
        # x, y = new_xy[:, 0], new_xy[:, 1]
        add_break_point(x, y, point_id=1)
        print(f"使用用户指定的倾泻点地理坐标 ({x}, {y}) 对应的栅格坐标")
    else:
        # 自动查找acc值最大的点坐标作为流域出口
        row0, col0 = np.unravel_index(np.argmax(acc), acc.shape)
        # 将行列坐标转换为地理坐标
        x, y = View.affine_transform(grid.affine, col0, row0)
        # 添加到break_point.geojson文件中
        add_break_point(x, y, point_id=1)
        print(f"自动选择流量累积最大值点作为倾泻点，地理坐标 ({x}, {y}) 对应的栅格坐标")
    catch = grid.catchment(
        x=x, y=y, fdir=fdir, dirmap=dirmap, xytype="coordinate", out_name="catch"
    )
    # grid.clip_to(catch)
    # clipped_catch = grid.view(catch)

    ### 使用polygonize方法获取流域边界  ###
    generate_watershed_boundary_with_rasterio(
        grid, catch, buffered_boundary_ori_geojson
    )

    river_ori = extract_river_network_with_threshold(
        acc,
        grid,
        fdir,
        Area_Threshold,
        cell_size_x=30,
        cell_size_y=30,
        threshold_percentile=99.7,
        dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
    )
    identified_streams = river_ori["identified_streams"]
    convert_branches_to_geojson(identified_streams, identified_streams_geojson)
    # 删除临时文件
    # os.remove(clipped_dem_path)


# -------------------------------------------------------- 生成子流域 -------------------------------------------------------------
# 填充洼地，生成流向、累积流、流域面
def process_dem_and_extract_watershed(
    dem_filename,
    tif_path,
    shapefile_path=None,
    x=None,
    y=None,
    dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
):
    grid = Grid.from_raster(tif_path)
    inflated_dem = grid.read_raster(tif_path, data_name="dem")
    ### D8方法计算流向 ###
    fdir = grid.flowdir(inflated_dem, dirmap=dirmap)

    ### 计算汇流累积量 (Flow Accumulation) ###
    acc0 = grid.accumulation(fdir=fdir, dirmap=dirmap, out_name="acc")
    grid.clip_to(inflated_dem)
    clipped_catch = grid.view(inflated_dem)
    # 裁剪acc和fdir
    acc = grid.view(acc0)
    fdir = grid.view(fdir)

    if "x" in locals() and "y" in locals() and x is not None and y is not None:
        add_break_point(x, y, point_id=1)
        print(f"使用用户指定的倾泻点地理坐标 ({x}, {y}) 对应的栅格坐标")
    else:
        # 自动查找acc值最大的点坐标作为流域出口
        row0, col0 = np.unravel_index(np.argmax(acc), acc.shape)
        # 将行列坐标转换为地理坐标
        x, y = View.affine_transform(grid.affine, col0, row0)
        # 添加到break_point.geojson文件中
        add_break_point(x, y, point_id=1)
        print(f"自动选择流量累积最大值点作为倾泻点，地理坐标 ({x}, {y}) 对应的栅格坐标")

    return grid, inflated_dem, fdir, acc, x, y, acc0


# 从保存的 DEM 文件重新构建 grid、fdir 和 acc
def load_grid_and_recompute(
    x, y, dem_path="inflated_dem.tif", dirmap=(64, 128, 1, 2, 4, 8, 16, 32)
):
    """
    从保存的 DEM 文件重新构建 grid、fdir 和 acc

    参数:
    dem_path : str
        已保存的 DEM 文件路径
    dirmap : tuple
        D8 流向编码映射

    返回:
    grid : Grid
        重建的 Grid 对象
    inflated_dem : Raster
        加载的 DEM 数据
    fdir : Raster
        流向数据
    acc : Raster
        汇流累积数据
    """
    # 重新加载 DEM 数据
    grid = Grid.from_raster(dem_path)
    inflated_dem = grid.read_raster(dem_path)

    ### D8方法计算流向 ###
    fdir = grid.flowdir(inflated_dem, dirmap=dirmap)
    ### 计算汇流累积量 (Flow Accumulation) ###
    acc = grid.accumulation(fdir=fdir, dirmap=dirmap, out_name="acc")



    catch = grid.catchment(
        x=x, y=y, fdir=fdir, dirmap=dirmap, xytype="coordinate", out_name="catch"
    )
    grid.clip_to(catch)
    clipped_catch = grid.view(catch)
    # 裁剪acc和fdir
    acc = grid.view(acc)
    fdir = grid.view(fdir)

    return grid, inflated_dem, fdir, acc


# -----------------------------------------------------------------------------------------------------------------------------
# 寻找汇水点（Junctions）及子流域出口点（upstream_cells）
def find_junctions_and_upstream_cells(
    grid, fdir, identified_streams, acc, x, y, flow_directions,break_point_geojson
):
    """
    寻找汇水点（Junctions）及子流域出口点（upstream_cells）

    参数:
    grid: Grid对象
    fdir: 流向数组
    identified_streams: 河道网络数组
    acc: 流量累积数组
    x: 倾泻点经度坐标
    y: 倾泻点纬度坐标
    flow_directions: 流向映射字典

    返回:
    tuple: (junctions, visited, node_ids, junction_count)
    """

    ###################################################################
    # 寻找汇水点（Junctions）及子流域出口点（upstream_cells）算法
    ##################################################################
    # 创建一个与流向栅格相同大小的空矩阵，用于标记汇水点（Junctions）
    junctions = np.zeros_like(fdir, dtype=int)
    visited = np.zeros_like(fdir, dtype=bool)  # 标记已访问的像元
    node_ids = np.zeros_like(fdir, dtype=int)  # 节点编号

    # 将地理坐标转换为行列坐标
    pour_col, pour_row = grid.nearest_cell(x, y)
    print(f"倾泻点地理坐标 ({x}, {y}) 对应的栅格坐标: col={pour_col}, row={pour_row}")

    # 存储待处理的分支点 (acc_value, row, col, junction_count)
    pending_branches = []
    # 从倾泻点开始处理
    current_path = [(pour_row, pour_col)]
    visited_count = 0
    node_id_counter = 1
    junction_count = 0
    path_count = 0
    upstream_data = {"type": "FeatureCollection", "features": []}

    # 获取所有break_point的行列坐标
    break_points_set, set_points, set_points_with_id = get_break_points(
        identified_streams, grid, fdir, flow_directions, break_point_geojson
    )

    # 主处理循环,寻找汇水点（Junctions）及子流域出口点（upstream_cells）
    current_node = (pour_row, pour_col)

    while current_node or pending_branches:
        if current_node:
            # 处理当前路径节点
            row, col = current_node

            # 如果已访问过，则跳过
            if visited[row, col]:
                # 当前路径结束
                path_count += 1
                print(f"第 {path_count} 条路径结束")

                # 从待处理分支中取出下一个分支
                if pending_branches:
                    # 按junction_count排序，处理较新的junction分支
                    pending_branches.sort(key=lambda x: x[3], reverse=True)
                    _, next_row, next_col, _ = pending_branches.pop()
                    current_node = (next_row, next_col)
                    print(
                        f"开始处理下一条路径，从待处理分支中取出节点: row={next_row}, col={next_col}"
                    )
                else:
                    current_node = None
                continue

            # 标记为已访问并分配节点ID
            visited[row, col] = True
            visited_count += 1
            node_ids[row, col] = node_id_counter
            node_id_counter += 1

            if visited_count % 1000 == 0:
                print(f"已遍历 {visited_count} 个像元...")
            # 先检查当前像元是否在河道上
            if identified_streams[row, col] != 1:
                continue

            # 查找当前像元的所有上游邻居
            upstream_cells = find_upstream_cells(
                row, col, fdir, identified_streams, flow_directions
            )

            # 检测junction点（有2个或更多上游邻居的点 或者 是break_point.geojson中的点（除第一个点外））
            is_junction = len(upstream_cells) >= 2 or (row, col) in break_points_set
            if is_junction:
                junctions[row, col] = 1
                junction_count += 1
                prev_junction_count = junction_count

                if junction_count <= 5:  # 前5个junction点输出详细信息
                    print(f"第 {junction_count} 个Junction点: row={row}, col={col}")
                    print(f"  该junction点有 {len(upstream_cells)} 个上游分支")

                # 立即写入geojson文件
                try:
                    # 将行列坐标转换为地理坐标（像素中心）
                    geo_x, geo_y = View.affine_transform(grid.affine, col+0.5, row+0.5)

                    # 创建点特征
                    point = {
                        "type": "Point",
                        "coordinates": [float(geo_x), float(geo_y)],
                    }

                    feature = {
                        "type": "Feature",
                        "geometry": point,
                        "properties": {
                            "id": int(junction_count),  # 按识别顺序编号
                            "row": int(row),
                            "col": int(col),
                            "node_id": int(node_ids[row, col]),
                        },
                    }

                    # 每次都创建新的数据结构（每次都从空文件开始）
                    data = {"type": "FeatureCollection", "features": []}

                    # 读取现有文件内容（如果存在）
                    try:
                        with open("junctions.geojson", "r", encoding="utf-8") as f:
                            existing_data = json.load(f)
                            # 使用现有文件中的所有特征
                            data["features"] = existing_data["features"]
                    except (FileNotFoundError, json.JSONDecodeError):
                        # 如果文件不存在或损坏，使用空的特征列表
                        pass

                    # 添加新特征
                    data["features"].append(feature)

                    # 写回文件
                    with open("junctions.geojson", "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)

                    print(f"Junction点 {junction_count} 已写入geojson文件")

                    # 按照流量累积量对上游像元排序，从大到小
                    sorted_upstream_cells = sorted(
                        [
                            (acc[up_row, up_col], up_row, up_col)
                            for up_row, up_col in upstream_cells
                        ],
                        key=lambda x: x[0],
                        reverse=True,
                    )

                    # 为每个上游像元创建特征
                    for idx, (acc_val, up_row, up_col) in enumerate(
                        sorted_upstream_cells
                    ):
                        # 计算编号：前缀为 junction_count，后缀为按流量排序的序号（从1开始）
                        cell_id = f"{junction_count}.{idx + 1}"

                        # 将行列坐标转换为地理坐标
                        up_geo_x, up_geo_y = View.affine_transform(
                            grid.affine, up_col, up_row
                        )

                        # 创建点特征
                        upstream_point = {
                            "type": "Point",
                            "coordinates": [float(up_geo_x), float(up_geo_y)],
                        }

                        # 构造属性字典
                        properties = {
                            "id": cell_id,
                            "junction_id": int(junction_count),
                            "upstream_order": idx + 1,
                            "flow_accumulation": int(acc_val),
                            "row": int(up_row),
                            "col": int(up_col),
                        }

                        # 如果该上游像元是break_point点，则添加set_ID属性
                        if (up_row, up_col) in set_points:
                            properties["break_point_ID"] = set_points_with_id[
                                (up_row, up_col)
                            ]

                        upstream_feature = {
                            "type": "Feature",
                            "geometry": upstream_point,
                            "properties": properties,
                        }

                        upstream_data["features"].append(upstream_feature)

                    # 写入 upstream_cells.geojson 文件
                    with open("upstream_cells.geojson", "w", encoding="utf-8") as f:
                        json.dump(upstream_data, f, ensure_ascii=False)
                    print(
                        f"Junction点 {junction_count} 的 {len(sorted_upstream_cells)} 个上游像元已写入upstream_cells.geojson文件"
                    )

                except ImportError:
                    print("json库未安装，无法保存为geojson文件")

                # 对上游分支按汇流累积量排序（优先处理大流量路径）
                upstream_with_acc = []
                for up_row, up_col in upstream_cells:
                    if not visited[up_row, up_col]:  # 只处理未访问的节点
                        acc_val = acc[up_row, up_col]
                        upstream_with_acc.append(
                            (acc_val, up_row, up_col, prev_junction_count)
                        )

                # 按acc值排序，第一个直接处理，其余存储到待处理分支
                upstream_with_acc.sort()

                if upstream_with_acc:
                    # 第一个节点用于继续当前路径
                    _, next_row, next_col, junction_id = upstream_with_acc[0]
                    current_node = (next_row, next_col)

                    # 其余节点存储为待处理分支
                    for _, up_row, up_col, junction_id in upstream_with_acc[1:]:
                        pending_branches.append(
                            (-(acc[up_row, up_col]), up_row, up_col, junction_id)
                        )
                    print(
                        f"Junction点有{len(upstream_with_acc)}个上游分支，继续处理第一个，其余{len(upstream_with_acc) - 1}个存储为待处理分支"
                    )
                else:
                    # 当前路径结束
                    path_count += 1
                    print(f"第 {path_count} 条路径结束")

                    # 从待处理分支中取出下一个分支
                    if pending_branches:
                        # 按junction_count排序，处理较新的junction分支
                        pending_branches.sort(key=lambda x: x[3], reverse=True)
                        _, next_row, next_col, _ = pending_branches.pop()
                        current_node = (next_row, next_col)
                        print(
                            f"开始处理下一条路径，从待处理分支中取出节点: row={next_row}, col={next_col}"
                        )
                    else:
                        current_node = None
            elif len(upstream_cells) == 1:
                # 非junction点：有1个上游节点，继续处理
                up_row, up_col = upstream_cells[0]
                if not visited[up_row, up_col]:
                    current_node = (up_row, up_col)

            else:
                # 没有上游节点（源头）
                # 当前路径结束
                path_count += 1
                print(f"第 {path_count} 条路径结束")

                # 从待处理分支中取出下一个分支
                if pending_branches:
                    # 按junction_count排序，处理较新的junction分支
                    pending_branches.sort(key=lambda x: x[3])
                    _, next_row, next_col, _ = pending_branches.pop()
                    current_node = (next_row, next_col)
                    print(
                        f"开始处理下一条路径，从待处理分支中取出节点: row={next_row}, col={next_col}"
                    )
                else:
                    current_node = None
        else:
            # 处理完所有路径
            break

    print(f"总共遍历了 {visited_count} 个像元")
    print(f"共找到 {junction_count} 个junction点")
    print(f"共处理了 {path_count} 条路径")
    print(f"节点编号范围: 1 到 {node_id_counter - 1}")

    return junction_count


# -----------------------------------------------------------------------------------------------------------------------------
# 生成子流域
def process_watershed_analysis(
    grid, fdir, identified_streams, acc, x, y, flow_directions, inflated_dem, dirmap, break_point_geojson
):
    """
    处理完整的流域分析流程，包括寻找汇水点、生成拓扑关系、划分子流域、检索源头点和生成河段

    参数:
    grid: Grid对象
    fdir: 流向数组
    identified_streams: 河道网络数组
    acc: 流量累积数组
    x: 倾泻点经度坐标
    y: 倾泻点纬度坐标
    flow_directions: 流向映射字典
    inflated_dem: 填洼后的DEM数据

    返回:
    dict: 包含分析结果的字典
    """
    # 定义 dirmap

    ###################################################################
    # 寻找汇水点（Junctions）及子流域出口点（upstream_cells）算法
    ##################################################################
    junction_count = find_junctions_and_upstream_cells(
        grid, fdir, identified_streams, acc, x, y, flow_directions, break_point_geojson
    )

    ###################################################################################
    # 生成河道拓扑关系表
    ###############################################################################
    # 调用函数构建upstream点之间的下游关系字典
    downstream_dict = build_upstream_downstream_relationships(
        "break_point.geojson",
        "upstream_cells.geojson",
        "source_deleted.geojson",
        identified_streams,
        grid,
        fdir,
        flow_directions,
        "downstream_dict.json",
    )
    print(f"\nupstream点之间的下游关系字典: {downstream_dict}")

    ###################################################################################
    # 划分子流域
    #################################################################################
    # 生成所有catchment
    all_catchments = generate_catchments_for_all_points(grid, fdir, dirmap)
    # 计算每个流域的独有区域
    unique_areas = compute_unique_areas(all_catchments)
    # 保存流域面积、中心点和边界到geojson文件
    save_all_catchments_to_single_geojson(
        unique_areas,
        grid,
        cell_size_x=30,
        cell_size_y=30,
        filename="sub_catchment.geojson",
    )  # 保存流域边界数据

    #####################################################################################
    # 检索源头点
    #####################################################################################
    # 检索源头点
    find_and_record_sources(
        identified_streams, fdir, flow_directions, junction_count, grid
    )

    ######################################################################################
    # 生成河段
    #####################################################################################
    # 调用函数生成河段LineString
    generate_river_network_linestrings(
        "junctions.geojson",  # 河流汇流点数据
        "break_point.geojson",  # 河流总出口及用户定义点
        "upstream_cells.geojson",  # 子流域出口点数据
        "river_network_linestrings.geojson",  # 输出的河段LineString数据
        identified_streams,
        grid,
        fdir,
        flow_directions,
    )

    # 添加geojson的河流长度属性
    add_river_length_to_geojson("river_network_linestrings.geojson")

    # 生成河段首尾坐标
    river_info0 = extract_river_network_info(
        "river_network_linestrings.geojson", inflated_dem, "junctions.geojson", grid
    )

    # 打印结果
    print("河流网络信息:")
    for riv_id, info in river_info0.items():
        print(
            f"'{riv_id}': {{\"length_km\": {info['length_km']}, \"From_point\": {info['From_point']}, \"To_point\": {info['To_point']}}}"
        )

    # 返回分析结果
    return downstream_dict, river_info0


# -----------------------------------------------------------------------------------------------------------------------------
# 将生成的文件移动到目录
def move_files_to_output_ori(random_folder_name):
    """
    将生成的文件移动到 output_ori 目录
    """
    # 确保目标目录存在，若不存在则自动创建
    # 生成一个随机的UUID作为文件夹名称

    # 使用随机文件夹名称作为父目录
    target_path = "output_ori"
    basic_file = "basic_file"
    target_directory = os.path.join(random_folder_name, target_path, basic_file)

    os.makedirs(target_directory, exist_ok=True)

    # # 创建预报方案1目录，与target_directory同级
    # target_path1 = "预报方案1"
    # forecast_plan_directory = os.path.join(random_folder_name, target_path1, basic_file)
    # os.makedirs(forecast_plan_directory, exist_ok=True)

    # 需要移动的文件列表
    files_to_move = [
        "junctions.geojson",
        "break_point.geojson",
        "sources.geojson",
        "sub_catchment.geojson",
        "upstream_cells.geojson",
        "downstream_dict.json",
        "river_network_linestrings.geojson",
        "identified_streams_linestring.geojson",
        "point.geojson",
        "source_deleted.geojson",
    ]

    # # 先将文件复制到预报方案1目录
    # for file_name in files_to_move:
    #     if os.path.exists(file_name):
    #         source_path = file_name
    #         forecast_target_path = os.path.join(forecast_plan_directory, file_name)
    #         shutil.copy2(source_path, forecast_target_path)  # 使用copy2保留文件元数据
    #         print(f"已复制 {file_name} 到 {forecast_plan_directory}")
    #     else:
    #         print(f"文件 {file_name} 不存在，无法复制")

    # 移动每个文件到原目标目录
    for file_name in files_to_move:
        if os.path.exists(file_name):
            source_path = file_name
            target_path = os.path.join(target_directory, file_name)
            shutil.move(source_path, target_path)
            print(f"已移动 {file_name} 到 {target_directory}")
        else:
            print(f"文件 {file_name} 不存在")
    return random_folder_name


# 将break_point和junction点文件合并
def merge_point_geojson(
    junctions_file="junctions.geojson",
    break_point_file="break_point.geojson",
    output_file="point.geojson",
):
    """
    合并junctions和break_point两个geojson文件，生成新的point.geojson文件

    参数:
    junctions_file: str, junctions.geojson文件路径
    break_point_file: str, break_point.geojson文件路径
    output_file: str, 输出文件路径，默认为"point.geojson"
    """
    import json

    # # 读取junctions文件
    # with open(junctions_file, "r", encoding="utf-8") as f:
    #     junctions_data = json.load(f)

    # 读取break_point文件
    with open(break_point_file, "r", encoding="utf-8") as f:
        break_point_data = json.load(f)

    # 创建新的FeatureCollection
    merged_data = {"type": "FeatureCollection", "features": []}

    # # 添加junctions的features（保持原有id）
    # for feature in junctions_data["features"]:
    #     merged_data["features"].append(feature)

    # 添加break_point的features（修改id添加前缀）
    for feature in break_point_data["features"]:
        # 检查是否为id为1的点
        if feature["properties"]["id"] == 1:
            # 复制feature避免修改原数据
            new_feature = feature.copy()
            # 获取原id并添加前缀
            original_id = new_feature["properties"]["id"]
            new_feature["properties"]["id"] = f"break_point_{original_id}"
            merged_data["features"].append(new_feature)

    # 写入合并后的数据到新文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    print(f"成功合并文件，输出到: {output_file}")
    return output_file

# 处理路径，移除前缀的函数
def remove_path_prefix(full_path):
    # 获取前缀路径
    prefix = os.getenv("FORECAST_SAVE_PATH", "")
    # 处理前缀为空的情况
    if not prefix:
        return full_path
    
    # 标准化路径（处理不同系统的路径分隔符）
    full_path_norm = os.path.normpath(full_path)
    prefix_norm = os.path.normpath(prefix)
    
    # 确保前缀末尾有路径分隔符，避免部分匹配
    if not prefix_norm.endswith(os.sep):
        prefix_norm += os.sep
    
    # 检查完整路径是否以该前缀开头
    if full_path_norm.startswith(prefix_norm):
        # 移除前缀，只保留后面的部分
        result = full_path_norm[len(prefix_norm):]
    else:
        # 如果前缀不匹配，返回原路径
        result = full_path_norm
    
    return result
# -----------------------------------------------------------------------------------------------------------------------------


class Generate_subwatersheds:
    """
    Main MPC Service that implements all required functionality:
    1. Fill depressions, generate flow direction, accumulation, and watershed outlet
    2. Select threshold and generate identified streams
    3. Generate sub-watersheds
    4. Merge/delete watersheds and regenerate river topology
    5. Generate appropriate outputs based on operations performed
    """

    def __init__(
        self,
        xy=(None, None),
        area_threshold=None,
        shapefile_path=None,
        s_geojson=None,
        dem_path=None,
        control_points=None,
        random_folder_name=None,
        plan_name="-流域1",
        state_dir="temp_state",
        cell_size_x=30,
        cell_size_y=30,
        step=None,
    ):
        delete_geojson_files(mode="all")

        """Initialize the MPC service"""
        if random_folder_name is None:
            random_folder_name = os.path.join(
                os.getenv("FORECAST_SAVE_PATH", ""),
                (
                    "".join(random.choices(string.ascii_letters + string.digits, k=16))
                    + plan_name
                ),
            )
        target_path = "output_ori"

        os.makedirs(os.path.join(random_folder_name, state_dir), exist_ok=True)
        self.state_dir = os.path.join(random_folder_name, state_dir)

        self.random_folder_name = random_folder_name
        self.plan_name = plan_name

        buffered_boundary_ori_geojson = os.path.join(
            self.random_folder_name, "output_ori", "basic_file"
        )
        os.makedirs(buffered_boundary_ori_geojson, exist_ok=True)

        self.start_time = time.time()
        if control_points and len(control_points) > 0:
            first_point = control_points[0]
            self.xy = (first_point[0], first_point[1])  # 使用第一个控制点的坐标
        else:
            self.xy = xy  # 使用传入的xy参数或默认值(None, None)
        self.area_threshold = area_threshold
        self.shapefile_path = shapefile_path  # 添加这一行
        self.s_geojson = s_geojson
        self.identified_streams = None
        self.downstream_dict = {}
        self.river_info = {}
        self.dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
        self.offsets = [
            (1, 0),
            (1, -1),
            (0, -1),
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        ]
        self.flow_directions = dict(zip(self.dirmap, self.offsets))
        self.cell_size_x = cell_size_x
        self.cell_size_y = cell_size_y
        self.dem_path = dem_path
        self.tif_path = os.path.join(self.state_dir, "inflated_dem.tif")
        self.identified_streams_path = os.path.join(
            self.state_dir, "identified_streams.tif"
        )

        # 初始化控制点
        self.control_points = control_points if control_points is not None else []
        if step == 1:
            # 初始化空的geojson文件
            self._initialize_geojson_files()

        # 添加控制点到break_point.geojson
        self._add_control_points()

    def random_folder_name_r(self):

        return remove_path_prefix(self.random_folder_name)

    def acc_default_value(self):
        value = get_default_acc_value(
            self.shapefile_path,
            self.dem_path,
            self.tif_path,
            self.s_geojson,
            threshold_percentile=99.8,
            cell_size_x=30,
            cell_size_y=30,
            dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
        )
        return value

    def _initialize_geojson_files(self):
        """Initialize empty geojson files"""

        files_to_initialize = [
            "junctions.geojson",
            "break_point.geojson",
            "sources.geojson",
            "source_deleted.geojson",
            "upstream_cells.geojson",
        ]

        for filename in files_to_initialize:
            if not os.path.exists(filename):
                data = {"type": "FeatureCollection", "features": []}
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)

    def _add_control_points(self):
        """
        添加控制点到break_point.geojson文件
        控制点格式: [(x1, y1, id1), (x2, y2, id2), ...]
        第一个点(id=1)被视为流域总出口
        """
        # 如果没有提供控制点，直接返回
        if not self.control_points:
            return
        # 添加控制点
        for i, point in enumerate(self.control_points):
            if len(point) >= 2:
                x, y = point[0], point[1]
                # 如果提供了ID，则使用该ID，否则自动生成
                point_id = point[2] if len(point) > 2 else i + 1

                # 使用现有的add_break_point函数添加点
                add_break_point(x, y, point_id=point_id)
                print(f"已添加控制点: ({x}, {y}), ID: {point_id}")

    def step0_streams(self):
        buffered_boundary_ori_geojson = os.path.join(
            self.random_folder_name,
            "output_ori",
            "basic_file",
            "ori_buffered_boundary.geojson",
        )
        streams_ori_geojson = os.path.join(
            self.random_folder_name, "output_ori", "basic_file", "ori_streams.geojson"
        )
        generate_initial_boundary_and_river(
            self.dem_path,
            buffered_boundary_ori_geojson,
            streams_ori_geojson,
            self.tif_path,
            x=None,
            y=None,
            shapefile_path=self.shapefile_path,
            Area_Threshold=self.area_threshold,
            dirmap=(64, 128, 1, 2, 4, 8, 16, 32),
        )

        delete_geojson_files(mode="all")
        return (
            buffered_boundary_ori_geojson,
            streams_ori_geojson,
            self.random_folder_name,
        )

    def step1_fill_depressions_and_flow(self):
        """
        Step 1: Fill depressions and generate flow direction, accumulation, and watershed outlet point

        Parameters:
        dem_path (str): Path to the DEM TIF file
        shapefile_path (str, optional): Path to shapefile for DEM clipping
        pour_point_x (float, optional): Pour point longitude
        pour_point_y (float, optional): Pour point latitude

        Returns:
        dict: Results with grid, inflated_dem, fdir, acc, and xy coordinates
        """

        ###将break_point点吸附到河道上
        # 首先清除所有geojson文件
        grid = Grid.from_raster(self.tif_path)
        inflated_dem = grid.read_raster(self.tif_path, data_name="dem")
        ### D8方法计算流向 ###
        fdir = grid.flowdir(inflated_dem, dirmap=self.dirmap)
        ### 计算汇流累积量 (Flow Accumulation) ###
        acc0 = grid.accumulation(fdir=fdir, dirmap=self.dirmap, out_name="acc")

        rt = calculate_identified_streams(
            acc0,
            cell_size_x=30,
            cell_size_y=30,
            Area_Threshold=self.area_threshold,
            threshold_percentile=99.8
            )
        identified_streams = rt["identified_streams"]
        # 将break_point吸附到河道上
        if self.control_points and len(self.control_points) > 0:
            new_control_points = []
            for point in self.control_points:
                x, y = point[0], point[1]
                lon, lat, _, _ = snap_point_to_stream(x, y, identified_streams, grid, search_radius=10)
                print(f"已吸附控制点: ({x}, {y}) 到 ({lon}, {lat})")
                # 保留ID，使用新坐标
                new_control_points.append((lon, lat, point[2]))

            # 完全替换列表（解决引用问题）
            self.control_points = new_control_points
            first_point = self.control_points[0]
            self.xy = (first_point[0], first_point[1])  # 使用第一个控制点的坐标
            print(self.xy,self.control_points[0])
        # 重新生成 break_point.geojson
        with open("break_point.geojson", "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)

        for point in self.control_points:
            add_break_point(point[0], point[1], point_id=point[2])



        print("Step 1: Filling depressions and generating flow direction...")
        (pour_point_x, pour_point_y) = self.xy
        # Process DEM using existing function
        grid, inflated_dem, fdir, acc, pour_point_x, pour_point_y,acc0 = (
            process_dem_and_extract_watershed(
                self.dem_path,
                self.tif_path,
                self.shapefile_path,
                pour_point_x,
                pour_point_y,
                self.dirmap,
            )
        )

        self.xy = (pour_point_x, pour_point_y)

        print("Step 1 completed.")

        return {"xy": self.xy}

    def step2_identify_streams(self):
        """
        Step 2: Select threshold and generate identified streams

        Parameters:
        area_threshold (float, optional): Area threshold in km²
        threshold_percentile (float): Percentile for threshold calculation (default: 99.8)

        Returns:
        dict: Stream identification results
        """
        print("Step 2: Identifying streams...")
        x, y = self.xy
        print(f"Pour point: ({x}, {y})")
        grid, _, _, acc = load_grid_and_recompute(x, y, self.tif_path)

        # Use existing function to identify streams
        result = calculate_identified_streams(
            acc,
            self.cell_size_x,
            self.cell_size_y,
            self.area_threshold,
            threshold_percentile=99.8,
        )

        identified_streams = result["identified_streams"]

        # 保存 identified_streams 为 GeoTIFF 格式
        grid.to_raster(
            identified_streams,
            self.identified_streams_path,
            data_name="identified_streams",
        )

        print(f"River network pixel count: {result['stream_pixel_count']}")
        print(
            f"Flow accumulation threshold: {result['threshold_value']}, area threshold: {result['Area_Threshold']} km²"
        )
        print("Step 2 completed.")

        return {
            "stream_pixel_count": int(result["stream_pixel_count"]),
            "threshold_value": float(result["threshold_value"]),
            "Area_Threshold": float(result["Area_Threshold"]),
            "message": "Streams identified successfully",
        }

    def step3_generate_subwatersheds(self):
        """
        Step 3: Generate sub-watersheds

        Returns:
        dict: Sub-watershed generation status
        """
        x, y = self.xy
        grid, inflated_dem, fdir, acc = load_grid_and_recompute(x, y, self.tif_path)

        grid1 = Grid.from_raster(self.identified_streams_path)
        identified_streams = grid1.read_raster(self.identified_streams_path)

        print("Step 3: Generating sub-watersheds...")

        # Use existing function to process watershed analysis

        self.downstream_dict, self.river_info = process_watershed_analysis(
            grid,
            fdir,
            identified_streams,
            acc,
            x,
            y,
            self.flow_directions,
            inflated_dem,
            self.dirmap,
            break_point_geojson="break_point.geojson",
        )

        identified_streams_to_linestring_geojson(
            "sources.geojson",
            "junctions.geojson",
            grid,
            fdir,
            self.flow_directions,
            identified_streams,
            "identified_streams_linestring.geojson",
        )

        print("Sub-watershed generation completed.")
        return {"status": "sub-watersheds generated"}

    def generate_final_outputs(self):
        """
        Final output generation based on whether merge/delete operations were performed

        Returns:
        dict: Information about generated output files
        """
        print("Generating final outputs...")

        # 将生成的文件移动到目录
        merge_point_geojson()
        random_folder_name = self.random_folder_name
        move_files_to_output_ori(random_folder_name)
        # 确保output_ori目录存在
        output_dir = os.path.join(random_folder_name, "output_ori", "basic_file")
        # Standard outputs without merge/delete operations
        # outputs = {
        #     "random_folder_name": random_folder_name,
        #     "break_point.geojson": os.path.join( output_dir, "break_point.geojson"),
        #     "junctions.geojson": os.path.join(output_dir, "junctions.geojson"),
        #     "upstream_cells.geojson": os.path.join(output_dir, "upstream_cells.geojson"),
        #     "river_network_linestrings.geojson": os.path.join(output_dir, "river_network_linestrings.geojson"),
        #     "downstream_dict.json": os.path.join(output_dir, "downstream_dict.json"),
        #     "sub_catchment.geojson": os.path.join(output_dir, "sub_catchment.geojson")
        # }
        import json

        sub_watersheds_file = os.path.join(
            output_dir, "sub_catchment.geojson"
        )  # 假设你有这个面文件
        reaches_file = os.path.join(output_dir, "river_network_linestrings.geojson")
        junctions_file = os.path.join(output_dir, "junctions.geojson")
        break_points_file = os.path.join(output_dir, "break_point.geojson")
        break_points_1_file = os.path.join(output_dir, "point.geojson")
        outputs = {
            "prePath": remove_path_prefix(random_folder_name),
            # 1. 子流域 (类型: polygon)
            # 如果你的后端确实只生成了点来代表子流域，这里的 'polygon' 改为 'point'，
            # 但前端 GisView 如果期待 coordinates 数组，你可能需要去后端生成 Polygon
            "subWatersheds": parse_geojson_to_frontend(
                sub_watersheds_file, entity_type="polygon"
            ),
            # 2. 河段 (类型: line)
            "reaches": parse_geojson_to_frontend(reaches_file, entity_type="line"),
            # 3. 节点 (类型: point)
            "junctions": parse_geojson_to_frontend(junctions_file, entity_type="point"),
            # 4. 控制断点 (类型: point)
            "breakPoints": parse_geojson_to_frontend(
                break_points_1_file, entity_type="point"
            ),
        }
        for file, description in outputs.items():
            print(f"  - {file}: {description}")

        end_time = time.time()
        execution_time = end_time - self.start_time
        print(f"Total execution time: {execution_time:.2f} seconds")

        return outputs


# # dem_filename = "E:\DEMshuju\ASTGTMV003_N28E118_dem.tif"
# shapefile_path = "E:\\work\\2025\\通用系统算法\\算法代码\\测试数据\\Overall_Watershed_Boundary.shp"   # 用户输入流域shp
# dem_filename = r"E:\\work\\2025\\通用系统算法\\算法代码\\测试数据\\dem.tif"
#
# # 用户设置
# cell_size_x = 30  # 经度方向上的像元大小
# cell_size_y = 30  # 纬度方向上的像元大小
# # Area_Threshold = 85.93376220000009  #阈值km2
# Area_Threshold = 25 #阈值km2
# # 用户输入倾泻点
# # x, y = 127.133902, 42.947535   #流域总出口，必须设置为id=1、
# x = None
# y = None
# # add_break_point(x, y, point_id=1)
# # x1, y1 = 118.821945, 28.901938                #用户设置的点，比如水文站
# # x2, y2 = 118.708886, 28.818608                #用户设置的点，比如水文站
# # add_break_point(x1, y1, point_id = 2)                       #添加控制点到break_point.geojson
# # add_break_point(x2, y2, point_id = 3)                       #添加控制点到break_point.geojson
# state_dir = "./temp_state"
# os.makedirs(state_dir, exist_ok=True)
# tif_path = os.path.join(state_dir, "inflated_dem.tif")
# # 定义 dirmap 和对应的偏移量
#         # N    NE    E    SE    S    SW    W    NW
# dirmap = (64, 128, 1, 2, 4, 8, 16, 32)
# offsets = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]  # N, NE, E, SE, S, SW, W, NW
# flow_directions = dict(zip(dirmap, offsets))
# # 指定倾泻点坐标
# grid, inflated_dem, fdir, acc, x, y = process_dem_and_extract_watershed(dem_filename, tif_path,shapefile_path, x, y)
# ######################################################################### 选择阈值并生成Identified Streams图层 #########################################################################
# # 选择阈值并生成水系（Identified Streams）
# result = calculate_identified_streams(acc, cell_size_x, cell_size_y, Area_Threshold=Area_Threshold)
# # 获取结果
# identified_streams = result['identified_streams']

#
# # 1. 初始化服务
# #
# # 方式1: 在初始化时传入控制点列表
# # -------------------------------------------------------   输入数据   ---------------------------------------------------------
# # 用户定义点
# break_points = [
#     (105.22850641549441, 27.02879110992917, 1),  # 流域总出口，必须设置为id=1
#     (105.078092, 27.0575545, 2),  # 用户设置的点，比如水文站
#     (104.745588, 27.140069, 3)   # 用户设置的点，比如水文站
# ]
#
# dem_path = "规划云平台数据/流域生成测试栅格/basin_tif.tif"
# area_threshold = 87.0
# # id_to_delete = ['Watershed2.1']
#
#
# # -------------------------------------------------------   主程序   ---------------------------------------------------------
# service = Generate_subwatersheds(
#     area_threshold=area_threshold,
#     dem_path=dem_path,
#     control_points=break_points,
#     state_dir="./temp_state"
# )
#
# # 2. 执行第一步：填洼和流向分析
# step1_result = service.step1_fill_depressions_and_flow()
#
# # 3. 执行第二步：识别河流网络
# step2_result = service.step2_identify_streams()
#
# # 4. 执行第三步：生成子流域
# step3_result = service.step3_generate_subwatersheds()
#
# # -----------------------------------------------------   合并、删除流域   -------------------------------------------------------
# # 用户定义的流域合并或删除
# id_to_merge = ['Watershed1.1', 'Watershed1.2']
# # 5. 执行第四步：合并流域（可选）
# merge_result = service.step4_merge_or_delete_watersheds(
#     operation="merge",
#     watershed_ids=id_to_merge
# )
#
# # 用户定义的流域合并或删除
# id_to_delete = ['Watershed3.1', 'Watershed2.2']
# # 5. 执行第四步：删除流域（可选）
# delete_result = service.step4_merge_or_delete_watersheds(
#     operation="delete",
#     watershed_ids=id_to_delete
# )
#
#
# # 第一次生成流域绘图
# def plot_all_geodata_together():
#     """
#     将break_point.geojson、junctions.geojson、river_network_linestrings.geojson、
#     sources.geojson、upstream_cells.geojson以及identified_streams绘制在同一张图上
#     """
#     plt.figure(figsize=(15, 12))
#     # 读取流域边界数据
#     basins = gpd.read_file('sub_catchment_merge.geojson')
#     print(f"读取到 {len(basins)} 个流域")
#     # 获取所有流域的边界范围
#     total_bounds = basins.total_bounds  # [minx, miny, maxx, maxy]
#     print(f"流域边界范围: {total_bounds}")
#
#     ### 这里使用了固定的转换系数 111320，但实际上经纬度每度的距离会随着纬度变化而变化，特别是在高纬度地区误差会较大。
#     # 根据total_bounds[3](最大纬度)判断纬度区域并设置转换系数
#     if abs(total_bounds[3]) <= 30:
#         meters_per_degree = 111320  # 低纬度区
#     elif abs(total_bounds[3]) <= 45:
#         meters_per_degree = 111200  # 中低纬度区
#     elif abs(total_bounds[3]) <= 60:
#         meters_per_degree = 111000  # 中高纬度区
#     else:
#         meters_per_degree = 110800  # 高纬度区
#     # 绘制流域边界（如果存在sub_catchment.geojson）
#     try:
#         with open('sub_catchment.geojson', 'r', encoding='utf-8') as f:
#             catchment_data = json.load(f)
#
#         # 存储流域中心点信息用于标签显示
#         catchment_centroids_x = []
#         catchment_centroids_y = []
#         catchment_ids = []
#
#         for feature in catchment_data['features']:
#             if feature['geometry']['type'] == 'Polygon':
#                 coordinates = feature['geometry']['coordinates'][0]  # 外环坐标
#                 lons = [coord[0] for coord in coordinates]
#                 lats = [coord[1] for coord in coordinates]
#                 plt.fill(lons, lats, color='gray', alpha=0.3, zorder=1, label='Catchment Boundary')
#                 plt.plot(lons, lats, color='black', linewidth=1, alpha=0.5, zorder=2)
#             elif feature['geometry']['type'] == 'MultiPolygon':
#                 for polygon_coords in feature['geometry']['coordinates']:
#                     coordinates = polygon_coords[0]  # 外环坐标
#                     lons = [coord[0] for coord in coordinates]
#                     lats = [coord[1] for coord in coordinates]
#                     plt.fill(lons, lats, color='gray', alpha=0.3, zorder=1, label='Catchment Boundary')
#                     plt.plot(lons, lats, color='black', linewidth=1, alpha=0.5, zorder=2)
#
#             # 获取流域ID和中心点坐标
#             props = feature.get('properties', {})
#             catchment_id = props.get('id', 'N/A')
#             centroid_x = props.get('centroid_x')
#             centroid_y = props.get('centroid_y')
#
#             # 存储中心点信息
#             if centroid_x is not None and centroid_y is not None:
#                 catchment_centroids_x.append(centroid_x)
#                 catchment_centroids_y.append(centroid_y)
#                 catchment_ids.append(catchment_id)
#
#         # 绘制流域ID标签，将颜色从蓝色改为黑色
#         for x, y, id_label in zip(catchment_centroids_x, catchment_centroids_y, catchment_ids):
#             plt.text(x, y, str(id_label), fontsize=9, ha='center', va='center',
#                      bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8),
#                      zorder=3, weight='bold', color='black')  # 修改颜色为黑色
#
#     except FileNotFoundError:
#         print("未找到 sub_catchment.geojson 文件，跳过流域边界绘制")
#     except Exception as e:
#         print(f"读取或绘制 sub_catchment.geojson 时出错: {e}")
#
#     # 显示Identified Streams图层作为背景
#     # plt.imshow(identified_streams, cmap='Blues', alpha=0.5, extent=grid.extent)
#
#     # 绘制河段LineString
#     try:
#         with open('river_network_linestrings.geojson', 'r', encoding='utf-8') as f:
#             linestrings_data = json.load(f)
#
#         river_labels_x, river_labels_y, river_labels_text = [], [], []
#         for feature in linestrings_data['features']:
#             if feature['geometry']['type'] == 'LineString':
#                 coordinates = feature['geometry']['coordinates']
#                 lons = [coord[0] for coord in coordinates]
#                 lats = [coord[1] for coord in coordinates]
#                 plt.plot(lons, lats, color='blue', linewidth=1.0, alpha=0.8,
#                          label='River Segments' if 'River Segments' not in plt.gca().get_legend_handles_labels()[
#                              1] else "")
#
#                 # 为河段添加标签
#                 if len(lons) > 1 and len(lats) > 1:
#                     # 在河段中点添加ID标签
#                     mid_idx = len(lons) // 2
#                     mid_lon = lons[mid_idx]
#                     mid_lat = lats[mid_idx]
#                     riv_id = feature['properties'].get('Riv-ID', '')
#                     river_labels_x.append(mid_lon)
#                     river_labels_y.append(mid_lat)
#                     river_labels_text.append(riv_id)
#     except Exception as e:
#         print(f"读取或绘制river_network_linestrings.geojson时出错: {e}")
#
#     # 绘制break_point点
#     try:
#         with open('break_point.geojson', 'r', encoding='utf-8') as f:
#             break_point_data = json.load(f)
#
#         break_lons, break_lats = [], []
#         break_labels = []
#         for feature in break_point_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 break_lons.append(coords[0])
#                 break_lats.append(coords[1])
#                 break_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 直接绘制break_point点，不进行栅格中心处理
#         if break_lons and break_lats:
#             plt.scatter(break_lons, break_lats, color='purple', s=100, marker='D',
#                         edgecolors='black', linewidth=1, label='Break Points', zorder=4)
#     except Exception as e:
#         print(f"读取或绘制break_point.geojson时出错: {e}")
#
#     # 绘制junctions点
#     try:
#         with open('junctions.geojson', 'r', encoding='utf-8') as f:
#             junctions_data = json.load(f)
#
#         junction_lons, junction_lats = [], []
#         junction_labels = []
#         for feature in junctions_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 junction_lons.append(coords[0])
#                 junction_lats.append(coords[1])
#                 junction_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 对junctions点进行栅格中心处理
#         if junction_lons and junction_lats:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_junction_lons = [lon + 0.5 * cellsize_x for lon in junction_lons]
#             center_junction_lats = [lat - 0.5 * cellsize_y for lat in junction_lats]
#
#             plt.scatter(center_junction_lons, center_junction_lats, color='red', s=80, marker='o',
#                         edgecolors='black', linewidth=1, label='Junctions', zorder=4)
#     except Exception as e:
#         print(f"读取或绘制junctions.geojson时出错: {e}")
#
#     # 绘制upstream_cells点
#     try:
#         with open('upstream_cells.geojson', 'r', encoding='utf-8') as f:
#             upstream_data = json.load(f)
#
#         upstream_lons, upstream_lats = [], []
#         upstream_labels = []
#         for feature in upstream_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 upstream_lons.append(coords[0])
#                 upstream_lats.append(coords[1])
#                 upstream_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 对upstream_cells点进行栅格中心处理
#         if upstream_lons and upstream_lats:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_upstream_lons = [lon + 0.5 * cellsize_x for lon in upstream_lons]
#             center_upstream_lats = [lat - 0.5 * cellsize_y for lat in upstream_lats]
#
#             plt.scatter(center_upstream_lons, center_upstream_lats, color='orange', s=50, marker='s',
#                         edgecolors='black', linewidth=1, label='Upstream Cells', zorder=4)
#     except Exception as e:
#         print(f"读取或绘制upstream_cells.geojson时出错: {e}")
#
#     # 绘制所有点的ID标签（使用统一的方法处理）
#     # 绘制break_point点的ID标签
#     try:
#         if 'break_lons' in locals() and 'break_lats' in locals() and 'break_labels' in locals():
#             # 直接使用原始坐标绘制标签，不进行栅格中心处理
#             for lon, lat, label in zip(break_lons, break_lats, break_labels):
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制break_point标签时出错: {e}")
#
#     # 绘制junctions点的ID标签
#     try:
#         if 'junction_lons' in locals() and 'junction_lats' in locals() and 'junction_labels' in locals():
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_junction_lons = [lon + 0.5 * cellsize_x for lon in junction_lons]
#             center_junction_lats = [lat - 0.5 * cellsize_y for lat in junction_lats]
#
#             for lon, lat, label in zip(center_junction_lons, center_junction_lats, junction_labels):
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制junctions标签时出错: {e}")
#
#     # 绘制upstream_cells点的ID标签
#     try:
#         if 'upstream_lons' in locals() and 'upstream_lats' in locals() and 'upstream_labels' in locals():
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_upstream_lons = [lon + 0.5 * cellsize_x for lon in upstream_lons]
#             center_upstream_lats = [lat - 0.5 * cellsize_y for lat in upstream_lats]
#
#             for lon, lat, label in zip(center_upstream_lons, center_upstream_lats, upstream_labels):
#                 plt.text(lon, lat, str(label), fontsize=8, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=8, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制upstream_cells标签时出错: {e}")
#
#     # 绘制河段ID标签
#     try:
#         if river_labels_x and river_labels_y and river_labels_text:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_river_labels_x = [x + 0.5 * cellsize_x for x in river_labels_x]
#             center_river_labels_y = [y - 0.5 * cellsize_y for y in river_labels_y]
#
#             for lon, lat, label in zip(center_river_labels_x, center_river_labels_y, river_labels_text):
#                 plt.text(lon, lat, str(label), fontsize=8, ha='center', va='center',
#                          bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.7),
#                          zorder=5)
#     except Exception as e:
#         print(f"绘制河段标签时出错: {e}")
#
#     # 设置标题和坐标轴标签
#     plt.title("Complete River Network Map\n(All GeoData Layers Combined)", size=16)
#     plt.xlabel('Longitude', size=12)
#     plt.ylabel('Latitude', size=12)
#
#     # 添加图例到图框外部右侧
#     plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
#
#     # 显示网格
#     plt.grid(True, alpha=0.3)
#
#     # 调整布局并显示图像，留出图例空间
#     plt.tight_layout()
#     plt.subplots_adjust(right=0.8)
#     plt.show(block=True)
#     print("成功绘制所有地理数据的综合图")
# plot_all_geodata_together()
# # _merge文件绘图
# def plot_all_geodata_together():
#     """
#     将break_point.geojson、junctions.geojson、river_network_linestrings.geojson、
#     sources.geojson、upstream_cells.geojson以及identified_streams绘制在同一张图上
#     """
#     plt.figure(figsize=(15, 12))
#     # 读取流域边界数据
#     basins = gpd.read_file('sub_catchment_merge.geojson')
#     print(f"读取到 {len(basins)} 个流域")
#     # 获取所有流域的边界范围
#     total_bounds = basins.total_bounds  # [minx, miny, maxx, maxy]
#     print(f"流域边界范围: {total_bounds}")
#
#     ### 这里使用了固定的转换系数 111320，但实际上经纬度每度的距离会随着纬度变化而变化，特别是在高纬度地区误差会较大。
#     # 根据total_bounds[3](最大纬度)判断纬度区域并设置转换系数
#     if abs(total_bounds[3]) <= 30:
#         meters_per_degree = 111320  # 低纬度区
#     elif abs(total_bounds[3]) <= 45:
#         meters_per_degree = 111200  # 中低纬度区
#     elif abs(total_bounds[3]) <= 60:
#         meters_per_degree = 111000  # 中高纬度区
#     else:
#         meters_per_degree = 110800  # 高纬度区
#     # 绘制流域边界（如果存在sub_catchment.geojson）
#     try:
#         with open('sub_catchment_merge.geojson', 'r', encoding='utf-8') as f:
#             catchment_data = json.load(f)
#
#         # 存储流域中心点信息用于标签显示
#         catchment_centroids_x = []
#         catchment_centroids_y = []
#         catchment_ids = []
#
#         for feature in catchment_data['features']:
#             if feature['geometry']['type'] == 'Polygon':
#                 coordinates = feature['geometry']['coordinates'][0]  # 外环坐标
#                 lons = [coord[0] for coord in coordinates]
#                 lats = [coord[1] for coord in coordinates]
#                 plt.fill(lons, lats, color='gray', alpha=0.3, zorder=1, label='Catchment Boundary')
#                 plt.plot(lons, lats, color='black', linewidth=1, alpha=0.5, zorder=2)
#             elif feature['geometry']['type'] == 'MultiPolygon':
#                 for polygon_coords in feature['geometry']['coordinates']:
#                     coordinates = polygon_coords[0]  # 外环坐标
#                     lons = [coord[0] for coord in coordinates]
#                     lats = [coord[1] for coord in coordinates]
#                     plt.fill(lons, lats, color='gray', alpha=0.3, zorder=1, label='Catchment Boundary')
#                     plt.plot(lons, lats, color='black', linewidth=1, alpha=0.5, zorder=2)
#
#             # 获取流域ID和中心点坐标
#             props = feature.get('properties', {})
#             catchment_id = props.get('id', 'N/A')
#             centroid_x = props.get('centroid_x')
#             centroid_y = props.get('centroid_y')
#
#             # 存储中心点信息
#             if centroid_x is not None and centroid_y is not None:
#                 catchment_centroids_x.append(centroid_x)
#                 catchment_centroids_y.append(centroid_y)
#                 catchment_ids.append(catchment_id)
#
#         # 绘制流域ID标签，使用黑色字体
#         for x, y, id_label in zip(catchment_centroids_x, catchment_centroids_y, catchment_ids):
#             plt.text(x, y, str(id_label), fontsize=9, ha='center', va='center',
#                      bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8),
#                      zorder=3, weight='bold', color='black')
#
#     except FileNotFoundError:
#         print("未找到 sub_catchment_merge.geojson 文件，跳过流域边界绘制")
#     except Exception as e:
#         print(f"读取或绘制 sub_catchment_merge.geojson 时出错: {e}")
#
#     # 显示Identified Streams图层作为背景
#     # plt.imshow(identified_streams, cmap='Blues', alpha=0.5, extent=grid.extent)
#
#     # 绘制河段LineString
#     try:
#         with open('river_network_linestrings_merge.geojson', 'r', encoding='utf-8') as f:
#             linestrings_data = json.load(f)
#
#         river_labels_x, river_labels_y, river_labels_text = [], [], []
#         for feature in linestrings_data['features']:
#             if feature['geometry']['type'] == 'LineString':
#                 coordinates = feature['geometry']['coordinates']
#                 lons = [coord[0] for coord in coordinates]
#                 lats = [coord[1] for coord in coordinates]
#                 plt.plot(lons, lats, color='blue', linewidth=1.0, alpha=0.8,
#                          label='River Segments' if 'River Segments' not in plt.gca().get_legend_handles_labels()[
#                              1] else "")
#
#                 # 为河段添加标签
#                 if len(lons) > 1 and len(lats) > 1:
#                     # 在河段中点添加ID标签
#                     mid_idx = len(lons) // 2
#                     mid_lon = lons[mid_idx]
#                     mid_lat = lats[mid_idx]
#                     riv_id = feature['properties'].get('Riv-ID', '')
#                     river_labels_x.append(mid_lon)
#                     river_labels_y.append(mid_lat)
#                     river_labels_text.append(riv_id)
#     except Exception as e:
#         print(f"读取或绘制river_network_linestrings.geojson时出错: {e}")
#
#     # 绘制break_point点
#     try:
#         with open('break_point.geojson', 'r', encoding='utf-8') as f:
#             break_point_data = json.load(f)
#
#         break_lons, break_lats = [], []
#         break_labels = []
#         for feature in break_point_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 break_lons.append(coords[0])
#                 break_lats.append(coords[1])
#                 break_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 直接绘制break_point点，不进行栅格中心处理
#         if break_lons and break_lats:
#             plt.scatter(break_lons, break_lats, color='purple', s=100, marker='D',
#                         edgecolors='black', linewidth=1, label='Break Points', zorder=4)
#     except Exception as e:
#         print(f"读取或绘制break_point.geojson时出错: {e}")
#
#     # 绘制junctions点
#     try:
#         with open('junctions_merge.geojson', 'r', encoding='utf-8') as f:
#             junctions_data = json.load(f)
#
#         junction_lons, junction_lats = [], []
#         junction_labels = []
#         for feature in junctions_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 junction_lons.append(coords[0])
#                 junction_lats.append(coords[1])
#                 junction_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 对junctions点进行栅格中心处理
#         if junction_lons and junction_lats:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_junction_lons = [lon + 0.5 * cellsize_x for lon in junction_lons]
#             center_junction_lats = [lat - 0.5 * cellsize_y for lat in junction_lats]
#
#             plt.scatter(center_junction_lons, center_junction_lats, color='red', s=80, marker='o',
#                         edgecolors='black', linewidth=1, label='Junctions', zorder=4)
#     except Exception as e:
#         print(f"读取或绘制junctions.geojson时出错: {e}")
#
#     # 绘制upstream_cells点
#     try:
#         with open('upstream_cells_merge.geojson', 'r', encoding='utf-8') as f:
#             upstream_data = json.load(f)
#
#         upstream_lons, upstream_lats = [], []
#         upstream_labels = []
#         for feature in upstream_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 upstream_lons.append(coords[0])
#                 upstream_lats.append(coords[1])
#                 upstream_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 对upstream_cells点进行栅格中心处理
#         if upstream_lons and upstream_lats:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_upstream_lons = [lon + 0.5 * cellsize_x for lon in upstream_lons]
#             center_upstream_lats = [lat - 0.5 * cellsize_y for lat in upstream_lats]
#
#             plt.scatter(center_upstream_lons, center_upstream_lats, color='orange', s=50, marker='s',
#                         edgecolors='black', linewidth=1, label='Upstream Cells', zorder=4)
#     except Exception as e:
#         print(f"读取或绘制upstream_cells.geojson时出错: {e}")
#
#     # 绘制source_deleted点
#     try:
#         with open('source_deleted.geojson', 'r', encoding='utf-8') as f:
#             source_deleted_data = json.load(f)
#
#         source_deleted_lons, source_deleted_lats = [], []
#         source_deleted_labels = []
#         for feature in source_deleted_data['features']:
#             if feature['geometry']['type'] == 'Point':
#                 coords = feature['geometry']['coordinates']
#                 source_deleted_lons.append(coords[0])
#                 source_deleted_lats.append(coords[1])
#                 source_deleted_labels.append(feature['properties'].get('id', 'N/A'))
#
#         # 绘制source_deleted点（进行栅格中心处理）
#         if source_deleted_lons and source_deleted_lats:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_source_deleted_lons = [lon + 0.5 * cellsize_x for lon in source_deleted_lons]
#             center_source_deleted_lats = [lat - 0.5 * cellsize_y for lat in source_deleted_lats]
#
#             plt.scatter(center_source_deleted_lons, center_source_deleted_lats, color='cyan', s=100, marker='^',
#                         edgecolors='black', linewidth=1, label='Deleted Sources', zorder=4)
#     except FileNotFoundError:
#         print("未找到 source_deleted.geojson 文件，跳过绘制")
#     except Exception as e:
#         print(f"读取或绘制source_deleted.geojson时出错: {e}")
#
#     # 绘制所有点的ID标签（使用统一的方法处理）
#     # 绘制break_point点的ID标签
#     try:
#         if 'break_lons' in locals() and 'break_lats' in locals() and 'break_labels' in locals():
#             # 直接使用原始坐标绘制标签，不进行栅格中心处理
#             for lon, lat, label in zip(break_lons, break_lats, break_labels):
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制break_point标签时出错: {e}")
#
#     # 绘制junctions点的ID标签
#     try:
#         if 'junction_lons' in locals() and 'junction_lats' in locals() and 'junction_labels' in locals():
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_junction_lons = [lon + 0.5 * cellsize_x for lon in junction_lons]
#             center_junction_lats = [lat - 0.5 * cellsize_y for lat in junction_lats]
#
#             for lon, lat, label in zip(center_junction_lons, center_junction_lats, junction_labels):
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制junctions标签时出错: {e}")
#
#     # 绘制upstream_cells点的ID标签
#     try:
#         if 'upstream_lons' in locals() and 'upstream_lats' in locals() and 'upstream_labels' in locals():
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_upstream_lons = [lon + 0.5 * cellsize_x for lon in upstream_lons]
#             center_upstream_lats = [lat - 0.5 * cellsize_y for lat in upstream_lats]
#
#             for lon, lat, label in zip(center_upstream_lons, center_upstream_lats, upstream_labels):
#                 plt.text(lon, lat, str(label), fontsize=8, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=8, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制upstream_cells标签时出错: {e}")
#
#     # 绘制source_deleted点的ID标签
#     try:
#         if 'source_deleted_lons' in locals() and 'source_deleted_lats' in locals() and 'source_deleted_labels' in locals():
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_source_deleted_lons = [lon + 0.5 * cellsize_x for lon in source_deleted_lons]
#             center_source_deleted_lats = [lat - 0.5 * cellsize_y for lat in source_deleted_lats]
#
#             for lon, lat, label in zip(center_source_deleted_lons, center_source_deleted_lats, source_deleted_labels):
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='white', weight='bold', zorder=5)
#                 plt.text(lon, lat, str(label), fontsize=9, ha='center', va='center',
#                          color='black', weight='bold', zorder=4,
#                          path_effects=[patheffects.withStroke(linewidth=2, foreground='black')])
#     except Exception as e:
#         print(f"绘制source_deleted标签时出错: {e}")
#
#     # 绘制河段ID标签
#     try:
#         if river_labels_x and river_labels_y and river_labels_text:
#             # 计算栅格分辨率
#             cellsize_x = 30/meters_per_degree  # 经度方向上的栅格大小
#             cellsize_y = 30/meters_per_degree  # 纬度方向上的栅格大小
#
#             # 将点从栅格左上角移动到中心
#             # 经度加0.5倍的栅格宽度，纬度减0.5倍的栅格高度（因为y轴方向是相反的）
#             center_river_labels_x = [x + 0.5 * cellsize_x for x in river_labels_x]
#             center_river_labels_y = [y - 0.5 * cellsize_y for y in river_labels_y]
#
#             for lon, lat, label in zip(center_river_labels_x, center_river_labels_y, river_labels_text):
#                 plt.text(lon, lat, str(label), fontsize=8, ha='center', va='center',
#                          bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.7),
#                          zorder=5)
#     except Exception as e:
#         print(f"绘制河段标签时出错: {e}")
#
#     # 设置标题和坐标轴标签
#     plt.title("Complete River Network Map\n(All GeoData Layers Combined)", size=16)
#     plt.xlabel('Longitude', size=12)
#     plt.ylabel('Latitude', size=12)
#
#     # 添加图例到图框外部右侧
#     plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
#
#     # 显示网格
#     plt.grid(True, alpha=0.3)
#
#     # 调整布局并显示图像，留出图例空间
#     plt.tight_layout()
#     plt.subplots_adjust(right=0.8)
#     plt.show(block=True)
#     print("成功绘制所有地理数据的综合图")
# plot_all_geodata_together()
#
# # 6. 生成最终输出
# outputs = service.generate_final_outputs()
