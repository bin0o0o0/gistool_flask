#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MPC Service for DEM-based Watershed Analysis

This service provides functionality for:
1. Filling depressions, generating flow direction, accumulation, and watershed outlet
2. Selecting threshold and generating identified streams
3. Generating sub-watersheds
4. Merging/deleting watersheds and regenerating river topology
5. Generating appropriate outputs based on operations performed

Author: Assistant
"""
import matplotlib.pyplot as plt
from pysheds.grid import Grid
import seaborn as sns
from geopy.distance import geodesic
from shapely.geometry import Point, Polygon, MultiPolygon, LineString, shape, mapping
from rasterio.mask import mask
import re
import glob
import shutil
import os
import json
import numpy as np
import geopandas as gpd
from pysheds.sview import View
from shapely.ops import unary_union
import tempfile
import rasterio
from rasterio import features
from scipy.spatial import Voronoi
from shapely.ops import polygonize
import warnings
import time
import uuid
import pickle
import os
import sys
from typing import Dict, Any, List, Optional, Union
from matplotlib import patheffects

from app.gis.watershed_core.parse_geojson_to_frontend import parse_geojson_to_frontend

warnings.filterwarnings("ignore")
sns.set_palette("pastel")


####   1.河道追踪相关算法   ####
# 将点吸附到最近的河道像元
def snap_point_to_stream(x, y, identified_streams, grid, search_radius=1):
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
    row, col : int
        吸附后的行列坐标，如果未找到则返回None
    """
    # 将地理坐标转换为行列坐标
    col, row = grid.nearest_cell(x, y)

    # 检查点是否已经在河道上
    if (
        0 <= row < identified_streams.shape[0]
        and 0 <= col < identified_streams.shape[1]
        and identified_streams[row, col] == 1
    ):
        return row, col

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

    return closest_row, closest_col if closest_row is not None else (row, col)


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
def get_break_points(identified_streams, grid, fdir, flow_directions):
    break_points = set()
    set_point = set()
    set_points_with_id = {}  # 用于存储点坐标和对应的ID
    try:
        with open("break_point.geojson", "r", encoding="utf-8") as f:
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
                if point_id == first_point_id:
                    continue

                # 将地理坐标转换为行列坐标
                x, y = coords[0], coords[1]
                row, col = snap_point_to_stream(x, y, identified_streams, grid)
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
    geo_x, geo_y = View.affine_transform(grid.affine, col, row)

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
    2. 遍历所有输入点，以输入的点(junctions和break_point_1)为起点，沿着河道（identified_streams）往下游进行遍历，直到找到另一个输入点为止
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
                # print(f"从 {start_id} 到流域出口，包含 {len(path)} 个栅格")
                end_id = "outlet"
                break

            next_row, next_col = downstream_cell

            # 添加到路径中
            path.append((next_row, next_col))

            # 检查是否到达了另一个输入点
            if (next_row, next_col) in input_points:
                end_id = input_points[(next_row, next_col)]
                # print(f"从 {start_id} 到 {end_id} 找到路径，包含 {len(path)} 个栅格")
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
                geo_x, geo_y = View.affine_transform(grid.affine, col + 0.5, row + 0.5)
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
            # print(f"创建河段: 从 {start_id} 到 {end_id}，长度 {len(path)}, Riv-ID: {riv_id}")

    # 保存到文件
    # 处理重复的Riv-ID
    linestrings_data = _resolve_duplicate_riv_ids(linestrings_data)
    try:
        with open(river_network_linestrings, "w", encoding="utf-8") as f:
            json.dump(linestrings_data, f, ensure_ascii=False)
        print(f"成功生成 {len(linestrings_data['features'])} 条河段LineString")
    except Exception as e:
        print(f"保存river_network_linestrings.geojson时出错: {e}")


def _resolve_duplicate_riv_ids(linestrings_data):
    """
    处理重复的Riv-ID，为重复的Riv-ID添加后缀。
    例如：两个"2.1"会变成"2.1.1"和"2.1.2"
    """
    from collections import defaultdict

    # 按Riv-ID分组
    riv_id_groups = defaultdict(list)
    for feature in linestrings_data["features"]:
        riv_id = feature["properties"].get("Riv-ID")
        riv_id_groups[riv_id].append(feature)

    # 处理重复的组
    for riv_id, features in riv_id_groups.items():
        if len(features) > 1:
            for i, feature in enumerate(features, start=1):
                feature["properties"]["Riv-ID"] = f"{riv_id}.{i}"

    return linestrings_data


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

    print("河流长度计算完成")


####   6.合并\删除流域   ####
# 判断选中流域能否合并
def validate_catchment_merge(ids_to_merge, downstream_dict, junctions_geojson):
    """
    验证选定的流域是否可以合并，确保合并后不会影响拓扑结构

    参数:
    ids_to_merge: list, 需要合并的流域ID列表
    downstream_dict: dict, 流域间的下游关系字典

    返回:
    list: 验证通过的流域ID列表

    异常:
    ValueError: 当验证失败时抛出异常，说明具体原因
    """
    # 新增判断：检查ids_to_merge的数字位是否都存在于downstream_dict中
    missing_watersheds = []
    for watershed_id in ids_to_merge:
        # 特殊处理：如果 watershed_id 是 "Watershed1"，跳过验证
        if watershed_id == "Watershed1":
            continue

        # 提取不带"Watershed"前缀的ID
        id_no_prefix = (
            watershed_id.split("Watershed")[1]
            if "Watershed" in watershed_id
            else watershed_id
        )

        # 检查该ID是否存在于downstream_dict的键或值中
        if id_no_prefix not in downstream_dict and not any(
            id_no_prefix == v for v in downstream_dict.values()
        ):
            missing_watersheds.append(watershed_id)

    # 如果有缺失的流域，抛出异常
    if missing_watersheds:
        raise ValueError(f"所选流域不存在: {missing_watersheds}")

    # 创建一个新的downstream_dict副本，去除包含"source"的项
    filtered_downstream_dict = {}
    for key, value in downstream_dict.items():
        # 跳过包含"source"的项
        if "source" not in str(key) and "source" not in str(value):
            filtered_downstream_dict[key] = value

    # 使用过滤后的字典替换原来的downstream_dict
    downstream_dict = filtered_downstream_dict



    # # downstream_dict中的所有流域的整数位均为1，直接通过条件0验证（只有三个子流域）
    # # 检查downstream_dict中的所有流域的整数位是否均为1
    # all_have_integer_part_1 = False
    # for key in downstream_dict.keys():
    #     # 提取整数位 - 处理break_point格式
    #     if "break_point_" in str(key):
    #         # 提取break_point_后面的数字部分
    #         integer_part = str(key).replace("break_point_", "")
    #     elif '.' in str(key):
    #         integer_part = str(key).split('.')[0]
    #     else:
    #         integer_part = str(key)
    #     print(f"流域的整数位: {key}")
    #     if integer_part != '1':
    #         all_have_integer_part_1 = True
    #         print(f"流域的整数位不是1: {key}")
    #         break


    # # 条件0: Watershed1特殊验证（也就是验证watershed1.1和1.2是不是有上游，有上游的时候这三个流域不能合并）
    # if "Watershed1" in ids_to_merge and all_have_integer_part_1:
    #     print("检测到Watershed1，执行条件0验证")
    #
    #     # 1. 通过downstream_dict，找到break_point的所有相邻的上游流域记为upstream_of_1
    #     upstream_of_1 = []
    #     for upstream_id, downstream_id in downstream_dict.items():
    #         # 提取不带"Watershed"前缀的ID用于比较
    #         downstream_no_prefix = (
    #             downstream_id.split("break_point_")[1]
    #             if "break_point_" in downstream_id
    #             else downstream_id
    #         )
    #         print(f"downstream_no_prefix:{downstream_no_prefix}")
    #         if downstream_no_prefix == "1":
    #             full_upstream_id = f"Watershed{upstream_id}"
    #             upstream_of_1.append(full_upstream_id)
    #
    #     print(f"Watershed1的上游流域: {upstream_of_1}")
    #
    #     # 若upstream_of_1只有1个流域直接通过条件0
    #     if len(upstream_of_1) == 1:
    #         print("Watershed1只有1个上游流域，直接通过条件0")
    #     elif len(upstream_of_1) > 1:
    #         # 判断所选流域ids_to_merge中是否包含所有upstream_of_1
    #         if all(
    #             upstream_watershed in ids_to_merge
    #             for upstream_watershed in upstream_of_1
    #         ):
    #             print("所选流域包含所有upstream_of_1，继续条件0验证")
    #
    #             # 2. 判断upstream_of_1中是否同时包含junction点（通过downstream_dict判断）
    #             junction_watersheds = []
    #
    #             # 对于upstream_of_1中的每个流域，检查它有多少个上游流域
    #             for watershed_id in upstream_of_1:
    #                 # 提取不带"Watershed"前缀的ID用于在downstream_dict中查找
    #                 watershed_no_prefix = (
    #                     watershed_id.split("Watershed")[1]
    #                     if "Watershed" in watershed_id
    #                     else watershed_id
    #                 )
    #
    #                 # 统计有多少个上游流域流向当前流域
    #                 upstream_count = 0
    #                 for upstream_id, downstream_id in downstream_dict.items():
    #                     if downstream_id == watershed_no_prefix:
    #                         upstream_count += 1
    #
    #                 # 如果有1个以上相邻上游，则说明这个流域包含节点（junction点）
    #                 if upstream_count > 1:
    #                     junction_watersheds.append(watershed_id)
    #
    #             print(f"upstream_of_1中包含junction点的流域: {junction_watersheds}")
    #
    #             # 若流域都包含junction点则，不通过条件0
    #             if len(junction_watersheds) == len(upstream_of_1):
    #                 raise ValueError(
    #                     f"所有上游流域都包含junction点，无法合并Watershed1"
    #                 )
    #             # 若只有1个流域包含junction点则通过条件0
    #             elif len(junction_watersheds) <= 1:
    #                 print("upstream_of_1中最多只有1个流域包含junction点，通过条件0")
    #             else:
    #                 raise ValueError(f"多个上游流域包含junction点，无法合并Watershed1")
    #         else:
    #             # 不是所有upstream_of_1都在选中列表中
    #             missing_upstream = [
    #                 uw for uw in upstream_of_1 if uw not in ids_to_merge
    #             ]
    #             raise ValueError(
    #                 f"合并Watershed1需要同时选中所有上游流域，缺少: {missing_upstream}"
    #             )
    # else:
    #     print("未检测到Watershed1或只有三个子流域，跳过条件0验证")




    # # 条件0.1: 检查Watershed1.1和Watershed1.2的上游流域验证
    # if "Watershed1.1" in ids_to_merge and "Watershed1.2" in ids_to_merge:
    #     print("检测到Watershed1.1和Watershed1.2，执行条件-1验证")
    #
    #     # 查找Watershed1.1和Watershed1.2的所有上游子流域
    #     up_watershed = set()
    #
    #     # 查找Watershed1.1的所有上游流域
    #     watershed_1_1_no_prefix = "1.1"
    #     for upstream_id, downstream_id in downstream_dict.items():
    #         if downstream_id == watershed_1_1_no_prefix:
    #             up_watershed.add(f"Watershed{upstream_id}")
    #
    #     # 查找Watershed1.2的所有上游流域
    #     watershed_1_2_no_prefix = "1.2"
    #     for upstream_id, downstream_id in downstream_dict.items():
    #         if downstream_id == watershed_1_2_no_prefix:
    #             up_watershed.add(f"Watershed{upstream_id}")
    #
    #     print(f"Watershed1.1和Watershed1.2的所有上游子流域: {list(up_watershed)}")
    #
    #     # 检查ids_to_merge是否包含所有的上游流域
    #     missing_upstream = up_watershed - set(ids_to_merge)
    #
    #     if missing_upstream:
    #         raise ValueError(
    #             f"合并Watershed1.1和Watershed1.2需要同时选中其所有上游流域"
    #         )
    #     else:
    #         print("Watershed1.1和Watershed1.2的所有上游流域都在合并列表中，通过条件-1验证")
    # else:
    #     print("未检测到Watershed1.1和Watershed1.2同时存在，跳过条件-1验证")



    # 条件1: 验证所有流域每个流域至少与列表中其他某个流域满足以下条件之一：
    # a. 同一节点控制 或 b. 存在上下游关系
    for i in range(len(ids_to_merge)):
        id1 = ids_to_merge[i]
        found_match = False

        # 提取不带"Watershed"前缀的ID用于在downstream_dict中查找
        id1_no_prefix = "break_point_1" if id1 == "Watershed1" else (
            id1.split("Watershed")[1] if "Watershed" in id1 else id1)

        # 检查当前流域是否与列表中其他任何一个流域满足条件
        for j in range(len(ids_to_merge)):
            if i == j:
                continue  # 跳过自己

            id2 = ids_to_merge[j]
            # 提取不带"Watershed"前缀的ID用于在downstream_dict中查找
            id2_no_prefix = "break_point_1" if id2 == "Watershed1" else (
                id2.split("Watershed")[1] if "Watershed" in id2 else id2)

            # 提取节点控制编号 (如 "Watershed1.1" -> "1")
            node1 = id1_no_prefix.split(".")[0]
            node2 = id2_no_prefix.split(".")[0]

            # 检查是否为同一节点控制
            is_same_node = node1 == node2

            # 检查是否存在上下游关系
            has_downstream_relationship = (
                id1_no_prefix in downstream_dict
                and downstream_dict[id1_no_prefix] == id2_no_prefix
                or id2_no_prefix in downstream_dict
                and downstream_dict[id2_no_prefix] == id1_no_prefix
            )

            # 如果满足条件a（同一节点控制），则需要进一步检查是否包含junction点
            if is_same_node:
                # 检查这两个流域是否包含junction点（通过downstream_dict判断）
                id1_upstream_count = 0
                id2_upstream_count = 0

                # 统计id1的上游流域数量
                for upstream_id, downstream_id in downstream_dict.items():
                    if downstream_id == id1_no_prefix:
                        id1_upstream_count += 1

                # 统计id2的上游流域数量
                for upstream_id, downstream_id in downstream_dict.items():
                    if downstream_id == id2_no_prefix:
                        id2_upstream_count += 1

                # 如果两个流域都有1个以上相邻上游，则说明都包含junction点，不能合并
                if id1_upstream_count > 1 and id2_upstream_count > 1:
                    print(
                        f"流域 {id1} 和 {id2} 都在同一节点控制下且都包含junction点，无法合并"
                    )
                    continue  # 继续检查与其他流域的关系
                else:
                    # 如果不是都包含junction点，则可以合并
                    found_match = True
                    break
            elif has_downstream_relationship:
                # 如果满足条件b（存在上下游关系），则可以直接合并
                found_match = True
                break

        # 如果当前流域与列表中其他所有流域都不满足条件，则无法合并
        if not found_match:
            raise ValueError(f"无法合并")
    # 条件1.1: 当ids_to_merge的数量大于等于3时，检查相邻整数位组之间是否存在上下游关系
    if len(ids_to_merge) >= 3:
        # 提取流域ID中的整数位并分组
        integer_groups = {}  # {integer_part: [watershed_ids]}
        for watershed_id in ids_to_merge:
            # 提取 "Watershed10.1" 中的 "10"
            number_part = watershed_id.split("Watershed")[1]
            integer_part = int(number_part.split(".")[0])

            if integer_part not in integer_groups:
                integer_groups[integer_part] = []
            integer_groups[integer_part].append(watershed_id)

        # 按整数位排序
        sorted_integers = sorted(integer_groups.keys())

        # 检查是否存在相邻的整数位组
        has_adjacent_groups = False
        for i in range(len(sorted_integers) - 1):
            current_integer = sorted_integers[i]
            next_integer = sorted_integers[i + 1]

            # 检查是否相邻（相差为1）
            if next_integer - current_integer == 1:
                has_adjacent_groups = True
                break

        # 只有当存在相邻整数位组时才进行上下游关系检查
        if has_adjacent_groups:
            # 检查相邻整数位组之间是否存在上下游关系
            for i in range(len(sorted_integers) - 1):
                current_integer = sorted_integers[i]
                next_integer = sorted_integers[i + 1]

                # 只处理相邻的整数位（相差为1）
                if next_integer - current_integer == 1:
                    current_group = integer_groups[current_integer]
                    next_group = integer_groups[next_integer]

                    # 收集当前组所有流域的下游流域
                    downstream_watersheds = set()

                    # 对于当前组中的每个流域，检查其下游流域
                    for current_watershed in current_group:
                        current_id = (
                            current_watershed.split("Watershed")[1]
                            if "Watershed" in current_watershed
                            else current_watershed
                        )

                        # 如果当前流域有下游流域，记录下来
                        if current_id in downstream_dict:
                            downstream_id = downstream_dict[current_id]
                            full_downstream_id = f"Watershed{downstream_id}"
                            downstream_watersheds.add(full_downstream_id)

                    # 对于下一组中的每个流域，检查其下游流域
                    for next_watershed in next_group:
                        next_id = (
                            next_watershed.split("Watershed")[1]
                            if "Watershed" in next_watershed
                            else next_watershed
                        )

                        # 如果下一流域有下游流域，记录下来
                        if next_id in downstream_dict:
                            downstream_id = downstream_dict[next_id]
                            full_downstream_id = f"Watershed{downstream_id}"
                            downstream_watersheds.add(full_downstream_id)

                    # 检查是否存在直接的上下游关系（current_group -> next_group 或 next_group -> current_group）
                    has_direct_relationship = False

                    # 检查current_group是否有流域直接流向next_group中的流域
                    for current_watershed in current_group:
                        current_id = (
                            current_watershed.split("Watershed")[1]
                            if "Watershed" in current_watershed
                            else current_watershed
                        )

                        for next_watershed in next_group:
                            next_id = (
                                next_watershed.split("Watershed")[1]
                                if "Watershed" in next_watershed
                                else next_watershed
                            )

                            if (
                                current_id in downstream_dict
                                and downstream_dict[current_id] == next_id
                            ):
                                has_direct_relationship = True
                                break
                            elif (
                                next_id in downstream_dict
                                and downstream_dict[next_id] == current_id
                            ):
                                has_direct_relationship = True
                                break

                        if has_direct_relationship:
                            break

                    # 如果存在直接上下游关系，则直接通过条件1.1
                    if has_direct_relationship:
                        print(
                            f"相邻整数位组 {current_integer} 和 {next_integer} 之间存在直接上下游关系，直接通过条件1.1"
                        )
                        continue

                    # 如果不存在直接上下游关系，检查所有下游流域是否都在合并列表中
                    all_downstream_in_merge_list = True
                    for downstream_watershed in downstream_watersheds:
                        if downstream_watershed not in ids_to_merge:
                            all_downstream_in_merge_list = False
                            break

                    # 如果所有下游流域都在合并列表中，则通过条件1.1
                    if all_downstream_in_merge_list and len(downstream_watersheds) > 0:
                        print(
                            f"相邻整数位组 {current_integer} 和 {next_integer} 的所有下游流域都在合并列表中，通过条件1.1"
                        )
                        continue
                    elif len(downstream_watersheds) == 0:
                        # 如果没有下游流域，也通过条件1.1
                        print(
                            f"相邻整数位组 {current_integer} 和 {next_integer} 没有下游流域，通过条件1.1"
                        )
                        continue
                    else:
                        # 存在下游流域不在合并列表中，则验证失败
                        raise ValueError(
                            f"相邻整数位组 {current_integer} 和 {next_integer} 之间不存在直接上下游关系，且下游流域不在合并列表中，无法合并"
                        )
        else:
            # 没有相邻整数位，直接通过条件1.1
            print("没有相邻整数位，直接通过条件1.1")
    # 条件2: 找出数字位最小和最大的流域（基于整数位）
    # 提取流域ID中的数字部分并按整数位排序
    watershed_numbers = []
    for watershed_id in ids_to_merge:
        # 提取 "Watershed1.1" 中的 "1.1"
        number_part = watershed_id.split("Watershed")[1]
        # 分解为整数位和小数位
        parts = number_part.split(".")
        integer_part = int(parts[0])
        decimal_part = int(parts[1]) if len(parts) > 1 else 0
        watershed_numbers.append(
            (watershed_id, integer_part, decimal_part, number_part)
        )

    # 按整数位排序，如果整数位相同则按小数位排序
    watershed_numbers.sort(key=lambda x: (x[1], x[2]))

    # 获取整数位最小和最大的流域
    # 找出所有整数位最小的流域
    min_integer_part = watershed_numbers[0][1]
    min_watersheds = [
        item[0] for item in watershed_numbers if item[1] == min_integer_part
    ]

    # 找出所有整数位最大的流域
    max_integer_part = watershed_numbers[-1][1]
    max_watersheds = [
        item[0] for item in watershed_numbers if item[1] == max_integer_part
    ]

    # 获取对应的上游ID数字
    def get_upstream_node_id(watershed_id):
        """获取流域的上游节点ID数字"""
        # 提取不带"Watershed"前缀的ID
        id_no_prefix = (
            "break_point_1"
            if watershed_id == "Watershed1"
            else watershed_id.split("Watershed")[1]
            if "Watershed" in watershed_id
            else watershed_id
        )

        # 在downstream_dict中查找哪个流域的下游是当前流域(即查找上游流域)
        for upstream_key, downstream_value in downstream_dict.items():
            # 如果downstream_value等于当前流域ID，则upstream_key是其上游流域
            if downstream_value == id_no_prefix:
                # 返回上游流域的节点ID
                return int(upstream_key.split(".")[0])

        # 如果没有找到上游流域，返回该流域自身的节点ID
        return int(id_no_prefix.split(".")[0])+ 1

    # 在具有相同整数位的流域中，找出上游节点ID最大的
    # 获取最小整数位流域中上游节点ID最大的流域
    min_watershed = min_watersheds[0]
    print(f"min_watershed: {min_watersheds}")
    min_upstream_ids = []
    for w in min_watersheds:
        upstream_id = get_upstream_node_id(w)
        min_upstream_ids.append((w, upstream_id))
        print(f"w: {w}")
        print(f"upstream_id: {upstream_id}")
    # 选择上游节点ID最大的流域
    print(f"min_upstream_ids: {min_upstream_ids}")
    min_watershed = min(min_upstream_ids, key=lambda x: x[1])[0]
    print(f"min_watershed: {min_watershed}")
    # 获取最大整数位流域中上游节点ID最大的流域
    max_watershed = max_watersheds[0]
    max_upstream_ids = []
    for w in max_watersheds:
        upstream_id = get_upstream_node_id(w)
        max_upstream_ids.append((w, upstream_id))
    # 选择上游节点ID最大的流域
    max_watershed = max(max_upstream_ids, key=lambda x: x[1])[0]

    # 获取最小和最大流域的上游节点ID
    min_id = get_upstream_node_id(min_watershed)
    max_id = get_upstream_node_id(max_watershed)
    print("max_id: " + str(max_id))
    print("min_id: " + str(min_id))

    # 条件3: 验证 min_id 到 (max_id-1) 之间的节点控制的流域是否都在合并列表中
    # 收集 min_id 到 (max_id-1) 范围内所有节点控制的流域
    required_watersheds = set()

    # 首先读取junctions.geojson文件，获取所有存在的junction ID
    existing_junction_ids = set()
    try:
        with open(junctions_geojson, "r", encoding="utf-8") as f:
            junctions_data = json.load(f)
        for feature in junctions_data["features"]:
            if feature["geometry"]["type"] == "Point":
                junction_id = feature["properties"].get("id")
                if junction_id is not None:
                    existing_junction_ids.add(junction_id)
    except Exception as e:
        print(f"读取junctions.geojson时出错: {e}")

    # 去除range(min_id, max_id)中在junctions.geojson中不存在的节点
    valid_node_ids = []
    # 提取子流域个数
    # 提取所有的流域 ID（键和值）
    all_watershed_ids = set()
    # 添加字典中的键（上游流域）
    all_watershed_ids.update(downstream_dict.keys())
    # 添加字典中的值（下游流域）
    all_watershed_ids.update(downstream_dict.values())
    # 去除 "break_point_1" 这种非流域 ID 的特殊情况
    watershed_numb = {id for id in all_watershed_ids}
    # 新增条件：在 downstream_dict 中找到以 max_id 为整数位的流域 ID
    max_id_watersheds = [
        key for key in downstream_dict.keys()
        if str(key).startswith(f"{max_id-1}.")
    ]

    # 新增：获取 ids_to_merge 中所有流域 ID 的整数位
    node_ids_from_merge = set()
    for watershed_id in ids_to_merge:
        # 提取不带"Watershed"前缀的 ID
        id_no_prefix = (
            watershed_id.split("Watershed")[1]
            if "Watershed" in watershed_id
            else watershed_id
        )
        # 提取整数位（小数点前的部分）
        # 处理"Watershed1"这种没有小数点的情况
        if "." in id_no_prefix:
            integer_part = int(id_no_prefix.split(".")[0])
        else:
            # 对于"Watershed1"这种情况，直接提取整个数字
            integer_part = int(id_no_prefix)
        node_ids_from_merge.add(integer_part)
    # 删除 node_ids_from_merge 中值为 min_id-1 的点（如果存在）
    if (min_id - 1) in node_ids_from_merge:
        node_ids_from_merge.remove(min_id - 1)
        print(f"已从 node_ids_from_merge 中移除节点 {min_id-1}")

    # 添加条件：当min_id等于max_id时，valid_node_ids的值就是min_id
    if max_id - min_id == 1:
        if len(ids_to_merge) == 2:
            # 如果上游的流域中有2个，需要保留junction点
            if len(max_id_watersheds) == 2:
                # 首先过滤掉 "Watershed1" 这种元素（如果存在）
                filtered_ids = [ws_id for ws_id in ids_to_merge if ws_id != "Watershed1"]
                # 在过滤后的列表中找到整数位等于 max_id 的所有元素
                matching_elements = [
                    ws_id for ws_id in filtered_ids
                    if int(
                        ws_id.replace("Watershed", "").split(".")[0] if "." in ws_id.replace("Watershed", "") else int(
                            ws_id.replace("Watershed", ""))) == max_id-1
                ]

                watershed = matching_elements[0]
                id_no_prefix = watershed.replace("Watershed", "")
                # 检查max_id-1对应的流域是否存在上游
                if id_no_prefix in downstream_dict.values():
                    raise ValueError(
                        f"合并验证失败：不能进行合并，两个流域均存在上游"
                    )
                else:
                    print(f"无上游流域与其下游流域合并，不删这个节点")

            else :
                valid_node_ids.append(min_id)
                print(f"节点只控制单个流域流域间的 junction{min_id}点需要删除")
        else:
            valid_node_ids.append(min_id)
            print(f"同一个节点的流域以及相邻流域全被选中，删除这个节点")
    else:
        # 修改：使用 ids_to_merge 中提取的整数位范围
        for node_id in sorted(node_ids_from_merge):
            if node_id in existing_junction_ids:
                # 检查 Watershed{max_id}.1 是否在 ids_to_merge 中
                if node_id == max_id - 1:
                    # 首先过滤掉 "Watershed1" 这种元素（如果存在）
                    filtered_ids = [ws_id for ws_id in ids_to_merge if ws_id != "Watershed1"]
                    # 在过滤后的列表中找到整数位等于 max_id 的所有元素
                    matching_elements = [
                        ws_id for ws_id in filtered_ids
                        if int(
                            ws_id.replace("Watershed", "").split(".")[0] if "." in ws_id.replace("Watershed",
                                                                                                 "") else int(
                                ws_id.replace("Watershed", ""))) == node_id
                    ]

                    # 检查 matching_elements 中的流域是否存在上游
                    # 如果max_id控制的流域全被选中，去除junction点
                    if len(max_id_watersheds) == len(matching_elements):
                        valid_node_ids.append(node_id)
                        print(f"max_id节点node_id {node_id} 控制的流域均被选中，删这个节点")
                    # 如果max_id控制的流域，未被全部选中，需要进行进一步的判断
                    elif len(max_id_watersheds) > len(matching_elements):
                        watershed = matching_elements[0]
                        # 因为确定只有一个元素，直接取第一个
                        id_no_prefix = watershed.replace("Watershed", "")
                        if id_no_prefix in downstream_dict.values():
                            raise ValueError(
                                f"合并验证失败：不能进行合并，max_node对应的流域存在上游"
                            )
                        else:
                            print(f"无上游流域与其下游流域合并，不删这个节点")

                valid_node_ids.append(node_id)
                print(f"节点node_id {node_id} 在junctions.geojson中存在，已添加")
            else:
                print(f"节点 {node_id} 在junctions.geojson中不存在，已跳过")


    # 收集有效节点控制的流域
    # 新增：检查max_id控制的流域是不是都在id_to_merge中

    node_id_watersheds = [
        key for key in downstream_dict.keys()
        if str(key).startswith(f"{max_id-1}.")
    ]
    # 将这些流域转换为完整格式（带"Watershed"前缀）
    node_id_watersheds_full = [f"Watershed{w}" for w in node_id_watersheds]
    if all(watershed in ids_to_merge for watershed in node_id_watersheds_full):
        print(f"节点 {max_id-1} 控制的所有流域都在合并列表中")
    else:
        # 修改：只有当 max_id 在 valid_node_ids 中时才移除
        if max_id-1 in valid_node_ids:
            valid_node_ids.remove(max_id-1)
            print(f"节点 {max_id-1} 控制的流域不全在合并列表中，已从 valid_node_ids 中移除节点 {max_id-1}")
        else:
            print(f"节点 {max_id-1} 控制的流域不全在合并列表中，但节点 {max_id-1} 不在 valid_node_ids 中")

    # 收集有效节点控制的流域
    for node_id in valid_node_ids:
        for watershed_id in downstream_dict.keys():
            # 检查流域是否由该节点控制
            if watershed_id.startswith(f"{node_id}."):
                # 添加"Watershed"前缀以匹配 ids_to_merge 中的格式
                full_watershed_id = f"Watershed{watershed_id}"
                required_watersheds.add(full_watershed_id)
            # 也检查该节点是否是下游流域的控制节点
            downstream_id = downstream_dict[watershed_id]
            if isinstance(downstream_id, str) and downstream_id.startswith(
                    f"{node_id}."
            ):
                # 添加"Watershed"前缀以匹配 ids_to_merge 中的格式
                full_downstream_id = f"Watershed{downstream_id}"
                required_watersheds.add(full_downstream_id)

    # 检查所有需要的流域是否都在合并列表中
    missing_watersheds = required_watersheds - set(ids_to_merge)
    if missing_watersheds:
        raise ValueError(
            f"合并验证失败：以下流域必须同时合并才能保持拓扑结构完整性: {missing_watersheds}"
        )

    # 验证通过，打印可以合并的流域列表
    print(f"合并验证通过！以下流域可以合并: {ids_to_merge}")
    if valid_node_ids:
        print(f"中间包含的节点ID: {valid_node_ids}")

    # 验证通过，返回可以合并的流域列表
    return ids_to_merge, valid_node_ids


# 合并流域
def merge_subcatchments_by_id(geojson_file_path, catchment_ids):
    """
    根据指定的流域ID合并all_subcatchments.geojson中的流域，并生成合并后的多边形

    参数:
    geojson_file_path: str, all_subcatchments.geojson文件的路径
    catchment_ids: list, 需要合并的流域ID列表

    返回:
    list: 合并后的shapely多边形对象列表（只包含一个合并后的多边形）
    """
    # 读取GeoJSON文件
    with open(geojson_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 收集需要合并的流域多边形
    polygons_to_merge = []

    # 遍历所有特征
    for feature in data["features"]:
        # 检查是否为多边形类型
        if feature["geometry"]["type"] == "Polygon":
            # 获取流域ID
            catchment_id = feature["properties"].get("id")

            # 如果该流域ID在指定列表中，则添加到合并列表
            if catchment_id in catchment_ids:
                # 使用shapely的shape函数从GeoJSON几何创建多边形对象
                polygon = shape(feature["geometry"])
                polygons_to_merge.append(polygon)
        elif feature["geometry"]["type"] == "MultiPolygon":
            # 处理MultiPolygon类型
            catchment_id = feature["properties"].get("id")

            if catchment_id in catchment_ids:
                # 使用shapely的shape函数从GeoJSON几何创建多边形对象
                multipolygon = shape(feature["geometry"])
                polygons_to_merge.extend(list(multipolygon.geoms))

    # 如果没有找到匹配的流域
    if not polygons_to_merge:
        print(f"未找到ID为 {catchment_ids} 的流域")
        return []

    # 合并所有多边形
    # 使用unary_union进行合并，它可以处理重叠和邻接的多边形
    merged_polygon = unary_union(polygons_to_merge)

    # 确保只返回一个合并后的多边形
    if isinstance(merged_polygon, Polygon):
        # 如果结果是单个多边形，直接返回
        return [merged_polygon]
    elif isinstance(merged_polygon, MultiPolygon):
        # 如果结果是多个多边形，返回整个MultiPolygon作为一个对象
        # 这样在绘制时仍然可以正确处理
        return [merged_polygon]
    else:
        # 其他情况（如GeometryCollection）
        return [merged_polygon]


# 判断选中流域能否删除
def validate_catchment_delete(ids_to_delete, downstream_dict, junctions_geojson):
    """
    验证选定的流域是否可以删除，确保删除操作不会破坏流域拓扑结构
    优化后支持同时对多条干流上的子流域进行删除

    删除条件：
    1. 如果只选中一个流域且该流域没有上游，则可以直接删除
    2. 对于多个流域，必须选中从最下游流域开始的所有上游流域

    参数:
    ids_to_delete: list, 需要删除的流域ID列表
    downstream_dict: dict, 流域间的下游关系字典

    返回:
    tuple: (验证通过的流域ID列表（分组形式）, 需要删除的节点ID列表)

    异常:
    ValueError: 当验证失败时抛出异常，说明具体原因
    """
    # 新增判断：检查ids_to_delete的数字位是否都存在于downstream_dict中
    missing_watersheds = []
    for watershed_id in ids_to_delete:
        # 提取不带"Watershed"前缀的ID
        id_no_prefix = (
            watershed_id.split("Watershed")[1]
            if "Watershed" in watershed_id
            else watershed_id
        )
        # 检查该ID是否存在于downstream_dict的键或值中
        if id_no_prefix not in downstream_dict and not any(
            id_no_prefix == v for v in downstream_dict.values()
        ):
            missing_watersheds.append(watershed_id)

    # 如果有缺失的流域，抛出异常
    if missing_watersheds:
        raise ValueError(f"所选流域不存在: {missing_watersheds}")

    # 创建一个新的downstream_dict副本，去除包含"source"的项
    filtered_downstream_dict = {}
    for key, value in downstream_dict.items():
        # 跳过包含"source"的项
        if "source" not in str(key) and "source" not in str(value):
            filtered_downstream_dict[key] = value

    # 使用过滤后的字典替换原来的downstream_dict
    downstream_dict = filtered_downstream_dict

    # 条件1: 如果只选中一个流域
    if len(ids_to_delete) == 1:
        watershed_id = ids_to_delete[0]
        # 提取不带"Watershed"前缀的ID
        id_no_prefix = (
            watershed_id.split("Watershed")[1]
            if "Watershed" in watershed_id
            else watershed_id
        )

        # 检查该流域是否有上游流域
        has_upstream = False
        for upstream_id, downstream_id in downstream_dict.items():
            if downstream_id == id_no_prefix:
                has_upstream = True
                break

        # 如果没有上游流域，则可以直接删除
        if not has_upstream:
            print(f"流域 {watershed_id} 没有上游流域，可以直接删除")
            return ids_to_delete, []  # 返回空的valid_node_ids列表
        else:
            raise ValueError(
                f"流域 {watershed_id} 有上游流域，不能单独删除，请同时选中其所有上游流域"
            )

    # 存储所有验证通过的组
    validated_groups = []

    # 待处理的流域列表
    remaining_ids = set(ids_to_delete)

    # 循环处理直到所有流域都被处理
    while remaining_ids:
        # 条件1: 如果只选中一个流域
        if len(remaining_ids) == 1:
            watershed_id = list(remaining_ids)[0]
            # 提取不带"Watershed"前缀的ID
            id_no_prefix = (
                watershed_id.split("Watershed")[1]
                if "Watershed" in watershed_id
                else watershed_id
            )

            # 检查该流域是否有上游流域
            has_upstream = False
            for upstream_id, downstream_id in downstream_dict.items():
                if downstream_id == id_no_prefix:
                    has_upstream = True
                    break

            # 如果没有上游流域，则可以直接删除
            if not has_upstream:
                print(f"流域 {watershed_id} 没有上游流域，可以直接删除")
                validated_groups.append([watershed_id])
                remaining_ids.remove(watershed_id)
                continue  # 继续处理下一个流域
            else:
                raise ValueError(
                    f"流域 {watershed_id} 有上游流域，不能单独删除，请同时选中其所有上游流域"
                )

        # 条件2: 多个流域的情况
        # 找出选中流域中整数位最小的流域(最下游流域)
        watershed_numbers = []
        for watershed_id in remaining_ids:
            # 提取 "Watershed1.2" 中的 "1.2"
            number_part = watershed_id.split("Watershed")[1]
            # 分解为整数位和小数位
            parts = number_part.split(".")
            integer_part = int(parts[0])
            decimal_part = int(parts[1]) if len(parts) > 1 else 0
            watershed_numbers.append(
                (watershed_id, integer_part, decimal_part, number_part)
            )

        # 按整数位排序，如果整数位相同则按小数位排序
        watershed_numbers.sort(key=lambda x: (x[1], x[2]))

        # 获取整数位最小的流域(可能有多个)
        min_integer_part = watershed_numbers[0][1]
        min_watersheds = [
            item[0] for item in watershed_numbers if item[1] == min_integer_part
        ]
        print(f"最下游流域: {min_watersheds}")

        # 条件3: 根据 downstream_dict 找到所有 min_watersheds 中流域的所有上游，直至没有上游
        upstream_watersheds = set()
        upstream_watersheds.update(min_watersheds)  # 包含所有最下游流域

        # 递归查找所有上游流域
        def find_all_upstream(watershed_id):
            upstream_list = []
            watershed_no_prefix = (
                watershed_id.split("Watershed")[1]
                if "Watershed" in watershed_id
                else watershed_id
            )

            # 查找所有以该流域为下游的上游流域
            for upstream_id, downstream_id in downstream_dict.items():
                if downstream_id == watershed_no_prefix:
                    full_upstream_id = f"Watershed{upstream_id}"
                    upstream_list.append(full_upstream_id)
                    # 递归查找更上游的流域
                    upstream_list.extend(find_all_upstream(full_upstream_id))

            return upstream_list

        # 获取所有上游流域
        for min_watershed in min_watersheds:
            all_upstream = find_all_upstream(min_watershed)
            upstream_watersheds.update(all_upstream)

        print(f"从 {min_watersheds} 开始的所有上游流域: {upstream_watersheds}")

        # 条件4: 将 upstream_Watershed 与 ids_to_delete 对比
        ids_to_delete_set = set(remaining_ids)

        # 如果两个集合相同，则验证通过
        if upstream_watersheds == ids_to_delete_set:
            # 验证通过，将这组流域添加到结果中
            validated_groups.append(list(upstream_watersheds))

            # 从待处理列表中移除已验证的流域
            remaining_ids -= upstream_watersheds

        else:
            # 分析不匹配的原因
            missing_in_delete = upstream_watersheds - ids_to_delete_set
            extra_in_delete = ids_to_delete_set - upstream_watersheds

            if missing_in_delete and not extra_in_delete:
                # 缺少流域的情况
                missing_list = list(missing_in_delete)
                raise ValueError(f"还需要选中以下流域才能删除: {missing_list}")
            elif extra_in_delete and not missing_in_delete:
                # 多选了不属于同一流域系统的流域，移除这些流域继续处理
                print(
                    f"检测到不属于同一流域系统的流域: {list(extra_in_delete)}，将其从当前处理组中移除"
                )
                validated_groups.append(list(upstream_watersheds))
                # 从当前处理组中移除这些额外的流域
                remaining_ids -= upstream_watersheds
                # 继续下一轮循环处理
                continue
            else:
                # 混合情况
                error_msgs = []
                if missing_in_delete:
                    missing_list = list(missing_in_delete)
                    error_msgs.append(f"还需要选中以下流域才能删除: {missing_list}")
                if extra_in_delete:
                    extra_list = list(extra_in_delete)
                    error_msgs.append(
                        f"请一次仅对一条干流进行删除操作，以下流域不属于同一流域系统: {extra_list}"
                    )
                raise ValueError("; ".join(error_msgs))

    # 在所有组验证通过后，计算每组的中间节点ID
    all_valid_node_ids = []

    # 首先读取 junctions.geojson 文件，获取所有存在的junction ID
    existing_junction_ids = set()
    try:
        with open(junctions_geojson, "r", encoding="utf-8") as f:
            junctions_data = json.load(f)
        for feature in junctions_data["features"]:
            if feature["geometry"]["type"] == "Point":
                junction_id = feature["properties"].get("id")
                if junction_id is not None:
                    existing_junction_ids.add(junction_id)
    except Exception as e:
        print(f"读取 junctions.geojson 时出错: {e}")

    # 对每个验证通过的组计算中间节点
    for group in validated_groups:
        print(len(group))
        if len(group) == 0:
            print("空组，跳过")
            continue

        # 找出组内流域数字位最小和最大的流域
        group_watershed_numbers = []
        for watershed_id in group:
            # 提取 "Watershed1.2" 中的 "1.2"
            number_part = watershed_id.split("Watershed")[1]
            # 分解为整数位和小数位
            parts = number_part.split(".")
            integer_part = int(parts[0])
            decimal_part = int(parts[1]) if len(parts) > 1 else 0
            group_watershed_numbers.append(
                (watershed_id, integer_part, decimal_part, number_part)
            )

        # 按整数位排序，如果整数位相同则按小数位排序
        group_watershed_numbers.sort(key=lambda x: (x[1], x[2]))

        # 获取整数位最小和最大的流域
        min_watershed_id = group_watershed_numbers[0][0]
        max_watershed_id = group_watershed_numbers[-1][0]

        # 获取最小和最大流域的上游节点ID
        min_id = int(min_watershed_id.split("Watershed")[1].split(".")[0])
        max_id = int(max_watershed_id.split("Watershed")[1].split(".")[0])

        # 收集有效节点ID (与 validate_catchment_merge 中相同的逻辑)
        valid_node_ids = []
        for node_id in range(min_id, max_id + 1):
            print(f"node_id:{node_id}")
            if len(range(min_id, max_id + 1)) == 1:
                print(
                    f"len(range(min_id, max_id + 1)):{len(range(min_id, max_id + 1))}"
                )
                # 提取所有流域ID（即downstream_dict的键）
                all_watershed_ids = list(downstream_dict.keys())
                print(f"all_watershed_ids:{all_watershed_ids}")
                # 查找node_id整数位对应的流域ID数量
                controlled_watersheds = set()  # 确保流域ID不重复
                for watershed_id in all_watershed_ids:
                    # 检查流域ID是否以"node_id."开头，例如node_id=1匹配"1.1", "1.2"等
                    if watershed_id.startswith(f"{node_id}."):
                        controlled_watersheds.add(watershed_id)
                full_controlled_watershed_id = (
                    f"Watershed{list(controlled_watersheds)[0]}"
                )
                print(full_controlled_watershed_id)
                # if len(controlled_watersheds) == 1 and full_controlled_watershed_id in group:
                #     valid_node_ids.append(node_id)
                #     print(f"找到{len(controlled_watersheds)}个对应的流域: {controlled_watersheds}")
                if len(controlled_watersheds) == 2 and len(group) == 1:
                    print(f"节点{node_id}不能删除")
                else:
                    valid_node_ids.append(node_id)
            elif node_id in existing_junction_ids:
                valid_node_ids.append(node_id)
            else:
                print(f"节点 {node_id} 在 junctions.geojson 中不存在，已跳过")

        all_valid_node_ids.extend(valid_node_ids)

    # 去重 valid_node_ids
    all_valid_node_ids = list(set(all_valid_node_ids))

    print(f"删除验证通过！以下流域可以删除: {validated_groups}")
    if all_valid_node_ids:
        print(f"中间包含的节点ID: {all_valid_node_ids}")
    return validated_groups, all_valid_node_ids


# 删除流域
def delete_catchments_by_id(
    sub_catchment_geojson, sub_catchment_merge_geojson, catchment_ids
):
    """
    根据指定的流域ID从geojson文件中删除流域

    参数:
    geojson_file_path: str, sub_catchment.geojson文件的路径
    catchment_ids: list, 需要删除的流域ID列表

    返回:
    bool: 删除操作是否成功
    """
    try:
        # 读取GeoJSON文件
        with open(sub_catchment_geojson, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 过滤掉需要删除的流域
        original_count = len(data["features"])
        data["features"] = [
            feature
            for feature in data["features"]
            if feature["properties"]["id"] not in catchment_ids
        ]
        removed_count = original_count - len(data["features"])

        # 保存更新后的GeoJSON文件
        output_file_path = sub_catchment_merge_geojson
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"成功删除 {removed_count} 个流域:")
        for catchment_id in catchment_ids:
            print(f"  - {catchment_id}")
        print(f"更新后的文件已保存为: {output_file_path}")

        return True

    except Exception as e:
        print(f"删除流域时出错: {e}")
        return False


####   7.重新生成junction、流域出口（upstream_cells）、流域和河段   ####
# 根据是否合并\删除，设置所有geojson文件路径
def set_geojson_file_paths(random_folder_name, plan_name, chuangjian=True):
    """
    根据sub_catchment_merge.geojson是否存在来设置所有geojson文件路径
    """

    # 确保目标目录存在，若不存在则自动创建
    target_path1 = "basic_file"
    first_merge = "output_ori"
    target_directory = os.path.join(random_folder_name, first_merge, target_path1)
    target_directory1 = os.path.join(random_folder_name, plan_name, target_path1)
    # 检查合并结果是否完整存在。失败后的半成品不能作为下一次合并输入。
    required_merge_files = [
        "sub_catchment_merge.geojson",
        "upstream_cells_merge.geojson",
        "junctions_merge.geojson",
        "river_network_linestrings_merge.geojson",
        "downstream_dict_merge.json",
    ]
    use_merged_files = all(
        os.path.exists(os.path.join(target_directory1, file_name))
        for file_name in required_merge_files
    )
    if use_merged_files:
        print("检测到合并后的文件，使用合并后的geojson文件")
        sub_catchment = os.path.join(target_directory1, "sub_catchment_merge.geojson")
        upstream_cells = os.path.join(target_directory1, "upstream_cells_merge.geojson")
        junctions = os.path.join(target_directory1, "junctions_merge.geojson")
        river_network_linestrings = os.path.join(
            target_directory1, "river_network_linestrings_merge.geojson"
        )
        source_deleted = os.path.join(target_directory1, "source_deleted.geojson")
        # 从JSON文件中读取downstream_dict0
        try:
            with open(
                os.path.join(target_directory1, "downstream_dict_merge.json"),
                "r",
                encoding="utf-8",
            ) as f:
                downstream_dict_v = json.load(f)
            print("成功从downstream_dict_merge.json读取downstream_dict0")
        except Exception as e:
            print(f"读取downstream_dict_merge.json文件时出错: {e}")
            downstream_dict_v = {}
    else:
        print("未检测到合并后的文件，使用原始geojson文件")
        sub_catchment = os.path.join(target_directory, "sub_catchment.geojson")
        upstream_cells = os.path.join(target_directory, "upstream_cells.geojson")
        junctions = os.path.join(target_directory, "junctions.geojson")
        river_network_linestrings = os.path.join(
            target_directory, "river_network_linestrings.geojson"
        )
        source_deleted = "source_deleted.geojson"
        with open(
            os.path.join(target_directory, "downstream_dict.json"),
            "r",
            encoding="utf-8",
        ) as f:
            downstream_dict_v = json.load(f)
        if chuangjian:
            # 同时创建带merge后缀的文件
            merge_files = [
                "sub_catchment_merge.geojson",
                "upstream_cells_merge.geojson",
                "junctions_merge.geojson",
                "river_network_linestrings_merge.geojson",
            ]
            for file_name in merge_files:
                file_path = os.path.join(target_directory1, file_name)
                if not os.path.exists(file_path):
                    # 创建空的GeoJSON文件
                    empty_geojson = {"type": "FeatureCollection", "features": []}
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(empty_geojson, f, ensure_ascii=False, indent=2)
                    print(f"已创建缺失的geojson文件: {file_path}")

    return (
        sub_catchment,
        upstream_cells,
        junctions,
        river_network_linestrings,
        source_deleted,
        downstream_dict_v,
    )


def _resolve_merge_output_paths(random_folder_name, plan_name, *file_names):
    """Resolve step2 merge/delete output files into the plan basic_file folder."""
    output_dir = os.path.join(random_folder_name, plan_name, "basic_file")
    os.makedirs(output_dir, exist_ok=True)
    return tuple(
        file_name
        if os.path.isabs(file_name)
        else os.path.join(output_dir, file_name)
        for file_name in file_names
    )


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


# 重新生成删除后的catchment
def process_deleted_catchment(
    sub_catchment_geojson, sub_catchment_deleted_geojson, ids_to_delete
):
    """
    收集ids_to_delete中所有流域ID，并从sub_catchment.geojson中删除这些流域信息

    参数:
    sub_catchment_geojson: str, 原始流域GeoJSON文件路径
    sub_catchment_deleted_geojson: str, 删除后的流域GeoJSON文件输出路径
    ids_to_delete: list, 需要删除的流域ID列表
    """

    try:
        # 读取原始流域GeoJSON文件
        with open(sub_catchment_geojson, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 过滤掉需要删除的流域
        original_count = len(data["features"])
        data["features"] = [
            feature
            for feature in data["features"]
            if feature["properties"]["id"] not in ids_to_delete
        ]
        removed_count = original_count - len(data["features"])

        # 保存更新后的GeoJSON文件
        with open(sub_catchment_deleted_geojson, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"成功从流域文件中删除 {removed_count} 个流域:")
        for catchment_id in ids_to_delete:
            print(f"  - {catchment_id}")
        print(f"删除后的流域文件已保存为: {sub_catchment_deleted_geojson}")

    except Exception as e:
        print(f"处理删除流域时出错: {e}")


# 重新生成合并的catchment
def process_merged_catchment(
    sub_catchment_geojson, sub_catchment_merge_geojson, ids_to_merge0, merged_polygons
):
    """
    收集ids_to_merge中所有流域ID的数字部分，并根据这个ID在sub_catchment.geojson中删除相应的流域信息。
    将合并后的merged_polygons储存到sub_catchment.geojson中，其命名为'Watershed'+ids_to_merge找到数字部分中最小的流域ID

    参数:
    ids_to_merge: list, 需要合并的流域ID列表
    merged_polygons: list, 合并后的shapely多边形对象列表
    """

    # 1. 提取所有流域ID的数字部分
    numeric_parts = []
    for watershed_id in ids_to_merge0:
        number_part = extract_watershed_number("Watershed", watershed_id)
        numeric_parts.append(number_part)

    print(f"提取的流域ID数字部分: {numeric_parts}")

    # 2. 找到最小的数字部分
    sorted_parts = sorted(
        numeric_parts, key=lambda x: [int(part) for part in x.split(".")]
    )
    min_part = sorted_parts[0]
    print(f"最小的流域ID数字部分: {min_part}")

    # 3. 根据数字部分在sub_catchment.geojson中删除相应的流域信息
    if not numeric_parts:
        print("没有需要处理的流域ID")
        return

    # 获取需要删除的ID列表
    ids_to_remove = [f"Watershed{part}" for part in numeric_parts]
    print(f"需要合并的流域ID: {ids_to_remove}")

    # 读取sub_catchment.geojson文件
    try:
        with open(sub_catchment_geojson, "r", encoding="utf-8") as f:
            sub_catchment_data = json.load(f)
    except FileNotFoundError:
        print("未找到sub_catchment.geojson文件")
        sub_catchment_data = {"type": "FeatureCollection", "features": []}
    except Exception as e:
        print(f"读取sub_catchment.geojson文件时出错: {e}")
        return

    # 计算合并后的流域面积和有效像素数
    total_area_km2 = 0.0
    total_valid_cells = 0

    # 收集要删除的流域的属性信息
    for feature in sub_catchment_data["features"]:
        props = feature.get("properties", {})
        catchment_id = props.get("id", "")

        if catchment_id in ids_to_remove:
            # 累加面积和有效像素数
            total_area_km2 += props.get("area_km2", 0.0)
            total_valid_cells += props.get("valid_cells", 0)

    # 过滤掉需要删除的特征
    filtered_features = []
    removed_count = 0

    for feature in sub_catchment_data["features"]:
        props = feature.get("properties", {})
        catchment_id = props.get("id", "")

        # 如果该特征的ID在删除列表中，则跳过(不添加到filtered_features)
        if catchment_id in ids_to_remove:
            print(f"合并流域: {catchment_id}")
            removed_count += 1
        else:
            filtered_features.append(feature)

    # 4. 将合并后的merged_polygons添加到现有特征中
    if not merged_polygons:
        print("没有合并后的多边形需要保存")
        return

    # 将合并后的多边形转换为GeoJSON格式并添加到现有特征中
    polygon = merged_polygons[0]

    # 计算合并后流域的中心点（确保在流域内）
    # 使用shapely的centroid方法获取几何中心
    centroid = polygon.centroid
    centroid_x, centroid_y = centroid.x, centroid.y

    # 如果需要确保中心点在多边形内部，可以使用以下方法
    if not polygon.contains(centroid):
        # 如果几何中心不在多边形内，使用代表点（representative point）
        # representative_point总是在多边形内部
        representative_point = polygon.representative_point()
        centroid_x, centroid_y = representative_point.x, representative_point.y

    # 构建输出文件的属性，使用'Watershed' + 最小流域ID数字部分作为ID
    properties = {
        "id": f"Watershed{min_part}",
        "area_km2": round(total_area_km2, 3),
        "valid_cells": int(total_valid_cells),
        "centroid_x": round(centroid_x, 6),
        "centroid_y": round(centroid_y, 6),
    }

    # 将shapely多边形转换为GeoJSON格式
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon" if isinstance(polygon, Polygon) else "MultiPolygon",
            "coordinates": [],
        },
        "properties": properties,
    }

    if isinstance(polygon, Polygon):
        # 处理单个多边形
        feature["geometry"]["coordinates"] = [list(polygon.exterior.coords)]
        # 添加孔洞坐标（如果有的话）
        for interior in polygon.interiors:
            feature["geometry"]["coordinates"].append(list(interior.coords))
    elif isinstance(polygon, MultiPolygon):
        # 处理多个多边形
        feature["geometry"]["type"] = "MultiPolygon"
        coordinates = []
        for poly in polygon.geoms:
            poly_coords = [list(poly.exterior.coords)]
            for interior in poly.interiors:
                poly_coords.append(list(interior.coords))
            coordinates.append(poly_coords)
        feature["geometry"]["coordinates"] = coordinates

    filtered_features.append(feature)

    # 更新features列表
    sub_catchment_data["features"] = filtered_features

    # 保存修改后的文件
    try:
        with open(sub_catchment_merge_geojson, "w", encoding="utf-8") as f:
            json.dump(sub_catchment_data, f, ensure_ascii=False, indent=2)
        print(f"成功删除{removed_count}个流域，更新后的文件已保存")
        print(f"合并后的多边形已添加到sub_catchment.geojson，ID为: Watershed{min_part}")
        print(
            f"合并后流域信息 - 面积: {round(total_area_km2, 3)} km², 有效像素数: {int(total_valid_cells)}"
        )
        print(f"中心点坐标: ({round(centroid_x, 6)}, {round(centroid_y, 6)})")
    except Exception as e:
        print(f"保存sub_catchment.geojson文件时出错: {e}")
        return


# 重新生成upstream_and_junctions
def remove_upstream_and_junctions_after_merge(
    upstream_cells_geojson,
    upstream_cells_merge_geojson,
    junctions_geojson,
    junctions_merge_geojson,
    ids_to_merge0,
    downstream_dict,
    fdir,
    identified_streams,
    flow_directions,
    grid,
    valid_node_ids=None,
):
    """
    在合并流域后，根据ids_to_merge中的ID列表，
    删除除了最小ID以外的子流域出口点
    如果提供了valid_node_ids，则同时删除junctions.geojson中对应的节点点

    参数:
    ids_to_merge: list, 需要合并的流域ID列表
    valid_node_ids: list, 可选，需要删除的junction节点ID列表
    """

    # 提取ID中的数字部分
    numeric_parts = []
    for watershed_id in ids_to_merge0:
        number_part = extract_watershed_number("Watershed", watershed_id)
        numeric_parts.append(number_part)
    # 找到最小的数字部分
    # 按照数字大小排序，而不是字符串排序
    sorted_parts = sorted(
        numeric_parts, key=lambda x: [int(part) for part in x.split(".")]
    )
    min_part = sorted_parts[0]
    max_part = sorted_parts[-1]
    print(f"最小的流域ID数字部分: {min_part}")

    # 获取需要删除的ID列表(除了最小的)
    ids_to_remove = [part for part in numeric_parts if part != min_part]
    print(f"需要删除的上游像元ID: {ids_to_remove}")

    # 检查min_part对应的junction点是否控制两个及以上子流域
    min_part_upstream_count = 0
    min_part_upstream_features = []

    # 读取upstream_cells.geojson文件来检查min_part控制的子流域数量
    try:
        with open(upstream_cells_geojson, "r", encoding="utf-8") as f:
            upstream_data = json.load(f)

        for feature in upstream_data["features"]:
            props = feature.get("properties", {})
            upstream_id = str(props.get("id", ""))

            # 提取junction_id (即min_part)
            if "." in upstream_id:
                junction_id = upstream_id.split(".")[0]
                if junction_id == min_part.split(".")[0]:  # 比较整数部分
                    min_part_upstream_count += 1
                    min_part_upstream_features.append(feature)

        print(
            f"Junction点 {min_part.split('.')[0]} 控制的子流域数量: {min_part_upstream_count}"
        )

        # 如果min_part对应的junction点控制两个及以上子流域
        if min_part_upstream_count >= 2:
            # 检查这两个子流域是否都被用户选中
            all_selected = True
            selected_upstream_features = []

            for feature in min_part_upstream_features:
                props = feature.get("properties", {})
                upstream_id = str(props.get("id", ""))
                if upstream_id not in numeric_parts:
                    all_selected = False
                else:
                    selected_upstream_features.append(feature)

            print(f"所有子流域都被选中: {all_selected}")

            # 如果所有子流域都被选中，则执行特殊处理
            if all_selected and len(selected_upstream_features) >= 2:
                print(f"对流域 {min_part} 倾泻点执行特殊处理")

                # 步骤1: 找到min_part在upstream_cells.geojson对应的点，获取"row"和"col"信息
                min_part_feature = None
                for feature in upstream_data["features"]:
                    props = feature.get("properties", {})
                    upstream_id = str(props.get("id", ""))
                    if upstream_id == min_part:
                        min_part_feature = feature
                        break

                if min_part_feature:
                    min_part_props = min_part_feature.get("properties", {})
                    min_part_row = min_part_props.get("row")
                    min_part_col = min_part_props.get("col")
                    print(
                        f"找到min_part点的行列坐标: row={min_part_row}, col={min_part_col}"
                    )

                    # 步骤2: 通过"row"和"col"找到该点下游的第一个点的位置信息
                    downstream_cell = find_downstream_cell(
                        min_part_row,
                        min_part_col,
                        fdir,
                        identified_streams,
                        flow_directions,
                    )

                    if downstream_cell:
                        downstream_row, downstream_col = downstream_cell
                        print(
                            f"找到下游点坐标: row={downstream_row}, col={downstream_col}"
                        )

                        # 将行列坐标转换为地理坐标
                        try:
                            down_geo_x, down_geo_y = View.affine_transform(
                                grid.affine, downstream_col, downstream_row
                            )

                            # 步骤3: 替换原min_part在upstream_cells.geojson对应的点的"coordinates"、"col"和"row"信息
                            min_part_feature["geometry"]["coordinates"] = [
                                float(down_geo_x),
                                float(down_geo_y),
                            ]
                            min_part_props["row"] = int(downstream_row)
                            min_part_props["col"] = int(downstream_col)
                            print(f"已更新min_part点的信息到下游位置")

                            # 关键：标记这个特征已被修改，以便后续保存时能保留这些更改
                            min_part_feature["_modified"] = True
                            try:
                                with open(
                                    upstream_cells_merge_geojson, "w", encoding="utf-8"
                                ) as f:
                                    json.dump(
                                        upstream_data, f, ensure_ascii=False, indent=2
                                    )
                                print(
                                    "已保存更新后的 upstream_cells_merge.geojson 文件"
                                )
                            except Exception as e:
                                print(
                                    f"保存 upstream_cells_merge.geojson 文件时出错: {e}"
                                )

                        except Exception as e:
                            print(f"更新min_part点信息时出错: {e}")
                    else:
                        print("未找到下游点")
    except Exception as e:
        print(f"检查junction点控制子流域时出错: {e}")

    # 过滤掉需要删除的特征
    filtered_features = []
    removed_count = 0

    for feature in upstream_data["features"]:
        props = feature.get("properties", {})
        upstream_id = str(props.get("id", ""))

        # 如果该特征的ID在删除列表中，则跳过(不添加到filtered_features)
        if upstream_id in ids_to_remove:
            print(f"删除上游像元点: {upstream_id}")
            removed_count += 1
        else:
            filtered_features.append(feature)

    # 更新features列表
    upstream_data["features"] = filtered_features

    # 保存修改后的文件
    try:
        with open(upstream_cells_merge_geojson, "w", encoding="utf-8") as f:
            json.dump(upstream_data, f, ensure_ascii=False, indent=2)
        print(f"成功删除{removed_count}个上游像元点，更新后的文件已保存")
    except Exception as e:
        print(f"保存upstream_cells_merge.geojson文件时出错: {e}")

    # 如果提供了valid_node_ids，则删除对应的junction点
    if valid_node_ids:
        print(f"需要删除的junction节点ID: {valid_node_ids}")

        try:
            # 读取junctions.geojson文件
            with open(junctions_geojson, "r", encoding="utf-8") as f:
                junctions_data = json.load(f)
        except FileNotFoundError:
            print("未找到junctions.geojson文件")
            return
        except Exception as e:
            print(f"读取junctions.geojson文件时出错: {e}")
            return

        ###判断节点是不是河流尽头，若是则也要进行删除###
        # 从max_part提取junction ID
        max_junction_id = int(max_part.split(".")[0])
        print(f"最大流域ID对应的junction点: {max_junction_id}")
        # 检查这个junction点控制的子流域是否均在ids_to_merge0中
        # 获取所有流域ID（即downstream_dict的键）
        all_watershed_ids = list(downstream_dict.keys())
        # 获取这个junction点控制的子流域
        junction_controlled_watersheds = []
        for watershed_id in all_watershed_ids:
            # 提取junction_id
            junction_id = int(watershed_id.split(".")[0])
            if junction_id == max_junction_id:
                junction_controlled_watersheds.append(watershed_id)

        print(
            f"Junction {max_junction_id} 控制的子流域: {junction_controlled_watersheds}"
        )

        # 检查这些子流域是否都在ids_to_merge0中
        all_controlled_in_merge = all(
            f"Watershed{watershed_id}" in ids_to_merge0 or watershed_id in ids_to_merge0
            for watershed_id in junction_controlled_watersheds
        )
        if all_controlled_in_merge and junction_controlled_watersheds:
            print(f"Junction {max_junction_id} 控制的所有子流域都在合并列表中")

            # 利用downstream_dict0，查找这些子流域是否存在上游
            has_upstream = False
            for watershed_id in junction_controlled_watersheds:
                full_watershed_id = (
                    f"Watershed{watershed_id}"
                    if not watershed_id.startswith("Watershed")
                    else watershed_id
                )
                # 检查这个子流域是否在downstream_dict0中作为下游节点出现
                for upstream_id, downstream_id in downstream_dict.items():
                    if downstream_id == full_watershed_id:
                        print(f"子流域 {full_watershed_id} 存在上游流域 {upstream_id}")
                        has_upstream = True
                        break
                if has_upstream:
                    break

            # 如果这些子流域均不存在上游，则将这个junction点加入到valid_node_ids中
            if not has_upstream:
                print(
                    f"Junction {max_junction_id} 控制的子流域均无上游，将其加入合并列表"
                )
                if valid_node_ids and max_junction_id not in valid_node_ids:
                    valid_node_ids.append(max_junction_id)
            else:
                print(f"Junction {max_junction_id} 控制的子流域存在上游，按原逻辑处理")
        else:
            print(
                f"Junction {max_junction_id} 控制的子流域不全在合并列表中，按原逻辑处理"
            )

        # 过滤掉需要删除的junction特征
        filtered_junctions = []
        removed_junctions_count = 0

        for feature in junctions_data["features"]:
            props = feature.get("properties", {})
            junction_id = props.get("id")

            # 如果该junction的ID在删除列表中，则跳过(不添加到filtered_junctions)
            if junction_id in valid_node_ids:
                print(f"删除junction点: {junction_id}")
                removed_junctions_count += 1
            else:
                filtered_junctions.append(feature)

        # 更新features列表
        junctions_data["features"] = filtered_junctions

        # 保存修改后的文件
        try:
            with open(junctions_merge_geojson, "w", encoding="utf-8") as f:
                json.dump(junctions_data, f, ensure_ascii=False, indent=2)
            print(f"成功删除{removed_junctions_count}个junction点，更新后的文件已保存")
        except Exception as e:
            print(f"保存junctions_merge.geojson文件时出错: {e}")
    else:
        # 读取junctions.geojson文件
        with open(junctions_geojson, "r", encoding="utf-8") as f:
            junctions_data = json.load(f)
        with open(junctions_merge_geojson, "w", encoding="utf-8") as f:
            json.dump(junctions_data, f, ensure_ascii=False, indent=2)
        print("未提供valid_node_ids，跳过junction点删除操作")


# 重新生成删除后的upstream_and_junctions并生成suorce_deleted.geojson文件
def remove_upstream_and_junctions_after_delete(
    upstream_cells_geojson,
    upstream_cells_deleted_geojson,
    junctions_geojson,
    junctions_deleted_geojson,
    source_deleted_geojson,
    ids_to_merge0,
    downstream_dict,
    fdir,
    identified_streams,
    flow_directions,
    grid,
    valid_node_ids=None,
):
    """
    在删除流域后，处理相关的upstream点、junction点和source_deleted点

    参数:
    sub_catchment_deleted_geojson: str, 删除后的流域GeoJSON文件路径
    upstream_cells_geojson: str, 原始上游像元GeoJSON文件路径
    upstream_cells_deleted_geojson: str, 处理后的上游像元GeoJSON文件输出路径
    junctions_geojson: str, 原始junction点GeoJSON文件路径
    junctions_deleted_geojson: str, 处理后的junction点GeoJSON文件输出路径
    source_deleted_geojson: str, source_deleted点GeoJSON文件路径
    ids_to_delete: list, 需要删除的流域ID列表
    downstream_dict: dict, 下游关系字典
    fdir: array, 流向数组
    identified_streams: array, 河道网络数组
    flow_directions: dict, 流向映射字典
    grid: Grid, Grid对象
    """

    # 提取ID中的数字部分
    numeric_parts = []
    for watershed_id in ids_to_merge0:
        number_part = extract_watershed_number("Watershed", watershed_id)
        numeric_parts.append(number_part)
    # 找到最小的数字部分
    # 按照数字大小排序，而不是字符串排序
    sorted_parts = sorted(
        numeric_parts, key=lambda x: [int(part) for part in x.split(".")]
    )
    min_part = sorted_parts[0]
    max_part = sorted_parts[-1]
    print(f"最小的流域ID数字部分: {min_part}")

    # 获取需要删除的ID列表(与remove_upstream_and_junctions_after_merge不同，这里不保留最小的)
    ids_to_remove = [part for part in numeric_parts]  # 删除所有ID，包括最小的
    print(f"需要删除的上游像元ID: {ids_to_remove}")

    # 检查min_part对应的junction点是否控制子流域
    min_part_upstream_count = 0
    min_part_upstream_features = []

    # 读取upstream_cells.geojson文件来检查min_part控制的子流域数量
    try:
        with open(upstream_cells_geojson, "r", encoding="utf-8") as f:
            upstream_data = json.load(f)

        for feature in upstream_data["features"]:
            props = feature.get("properties", {})
            upstream_id = str(props.get("id", ""))

            # 提取junction_id (即min_part)
            if "." in upstream_id:
                junction_id = upstream_id.split(".")[0]
                if junction_id == min_part.split(".")[0]:  # 比较整数部分
                    min_part_upstream_count += 1
                    min_part_upstream_features.append(feature)

        print(
            f"Junction点 {min_part.split('.')[0]} 控制的子流域数量: {min_part_upstream_count}"
        )

        # 读取现有的source_deleted.geojson文件（如果存在）
        try:
            with open(source_deleted_geojson, "r", encoding="utf-8") as f:
                source_deleted_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            source_deleted_data = {"type": "FeatureCollection", "features": []}
            # 确保文件存在且格式正确
            with open(source_deleted_geojson, "w", encoding="utf-8") as f:
                json.dump(source_deleted_data, f, ensure_ascii=False, indent=2)
        # 根据新的规则处理source_deleted.geojson的生成
        if min_part_upstream_count == 1:
            # 如果min_part对应的junction点控制1个子流域
            # 将最小id的upstream_cell点的经纬度坐标和行列坐标提取出来，添加到source_deleted.geojson中
            if min_part_upstream_features:
                # 查找与min_part ID完全匹配的upstream_cell点
                min_feature = None
                for feature in min_part_upstream_features:
                    props = feature.get("properties", {})
                    upstream_id = str(props.get("id", ""))
                    if upstream_id == min_part:
                        min_feature = feature
                        break

                # 创建新特征并添加到source_deleted.geojson
                new_feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": min_feature["geometry"]["coordinates"][:],
                    },
                    "properties": {
                        "id": f"source_{min_part}",
                        "type": "point",
                        "row": min_feature["properties"]["row"],
                        "col": min_feature["properties"]["col"],
                    },
                }
                source_deleted_data["features"].append(new_feature)
                print(
                    f"已将控制1个子流域的junction点信息添加到source_deleted.geojson中"
                )
        elif min_part_upstream_count >= 2:
            # 如果min_part对应的junction点控制2个及以上子流域
            # 检查这些子流域是否都被用户选中
            selected_upstream_features = []
            for feature in min_part_upstream_features:
                props = feature.get("properties", {})
                upstream_id = str(props.get("id", ""))
                if upstream_id in numeric_parts:
                    selected_upstream_features.append(feature)

            print(
                f"被用户选中的子流域数量: {len(selected_upstream_features)}, 总控制子流域数量: {min_part_upstream_count}"
            )

            if len(selected_upstream_features) == min_part_upstream_count:
                # 所有子流域都被用户选中，执行特殊处理
                print(f"所有子流域都被选中，执行特殊处理")

                # 将最后找到的downstream_cell点的地理坐标和行列坐标添加到source_deleted.geojson中
                min_part_feature = None
                for feature in upstream_data["features"]:
                    props = feature.get("properties", {})
                    upstream_id = str(props.get("id", ""))
                    if upstream_id == min_part:
                        min_part_feature = feature
                        break

                if min_part_feature:
                    min_part_props = min_part_feature.get("properties", {})
                    min_part_row = min_part_props.get("row")
                    min_part_col = min_part_props.get("col")
                    print(
                        f"找到min_part点的行列坐标: row={min_part_row}, col={min_part_col}"
                    )

                    # 通过"row"和"col"找到该点下游的第一个点的位置信息
                    downstream_cell = find_downstream_cell(
                        min_part_row,
                        min_part_col,
                        fdir,
                        identified_streams,
                        flow_directions,
                    )

                    if downstream_cell:
                        downstream_row, downstream_col = downstream_cell
                        print(
                            f"找到下游点坐标: row={downstream_row}, col={downstream_col}"
                        )

                        # 将行列坐标转换为地理坐标
                        try:
                            down_geo_x, down_geo_y = View.affine_transform(
                                grid.affine, downstream_col, downstream_row
                            )

                            # 创建保存到source_deleted.geojson中的特征
                            new_feature = {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [
                                        float(down_geo_x),
                                        float(down_geo_y),
                                    ],
                                },
                                "properties": {
                                    "id": f"source_{min_part}",
                                    "type": "point",
                                    "row": int(downstream_row),
                                    "col": int(downstream_col),
                                },
                            }
                            source_deleted_data["features"].append(new_feature)
                            print(
                                f"已将控制多个子流域的junction点下游信息添加到source_deleted.geojson中"
                            )

                        except Exception as e:
                            print(f"更新min_part点信息时出错: {e}")
                    else:
                        print("未找到下游点")
            else:
                # 不是所有子流域都被用户选中，将最小id的upstream_cell点信息添加到source_deleted.geojson中
                if min_part_upstream_features:
                    # 查找与min_part ID完全匹配的upstream_cell点
                    min_upstream_feature = None
                    for feature in min_part_upstream_features:
                        props = feature.get("properties", {})
                        upstream_id = str(props.get("id", ""))
                        if upstream_id == min_part:
                            min_upstream_feature = feature
                            break

                    # 如果找到了完全匹配的点，则使用该点；否则使用ID最小的点
                    if min_upstream_feature is None:
                        min_upstream_feature = min(
                            min_part_upstream_features,
                            key=lambda f: f["properties"]["id"],
                        )
                        print(
                            f"警告：未找到与min_part ({min_part}) 完全匹配的upstream_cell点，使用ID最小的点"
                        )
                    else:
                        print(
                            f"已找到与min_part ({min_part}) 完全匹配的upstream_cell点"
                        )

                    # 创建新特征并添加到source_deleted.geojson
                    new_feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": min_upstream_feature["geometry"][
                                "coordinates"
                            ][:],
                        },
                        "properties": {
                            "id": f"source_{min_part}",
                            "type": "point",
                            "row": min_upstream_feature["properties"]["row"],
                            "col": min_upstream_feature["properties"]["col"],
                        },
                    }
                    source_deleted_data["features"].append(new_feature)
                    print(
                        f"已将最小ID的upstream_cell点信息添加到source_deleted.geojson中"
                    )

        # 保存source_deleted.geojson文件
        try:
            with open(source_deleted_geojson, "w", encoding="utf-8") as f:
                json.dump(source_deleted_data, f, ensure_ascii=False, indent=2)
            print("已更新source_deleted.geojson文件")
        except Exception as e:
            print(f"保存source_deleted.geojson文件时出错: {e}")

    except Exception as e:
        print(f"检查junction点控制子流域时出错: {e}")

    # 过滤掉需要删除的特征
    filtered_features = []
    removed_count = 0

    for feature in upstream_data["features"]:
        props = feature.get("properties", {})
        upstream_id = str(props.get("id", ""))

        # 如果该特征的ID在删除列表中，则跳过(不添加到filtered_features)
        if upstream_id in ids_to_remove:
            print(f"删除上游像元点: {upstream_id}")
            removed_count += 1
        else:
            filtered_features.append(feature)

    # 更新features列表
    upstream_data["features"] = filtered_features

    # 保存修改后的文件
    try:
        with open(upstream_cells_deleted_geojson, "w", encoding="utf-8") as f:
            json.dump(upstream_data, f, ensure_ascii=False, indent=2)
        print(f"成功删除{removed_count}个上游像元点，更新后的文件已保存")
    except Exception as e:
        print(f"保存upstream_cells_deleted.geojson文件时出错: {e}")

    # 如果提供了valid_node_ids，则删除对应的junction点
    if valid_node_ids:
        print(f"需要删除的junction节点ID: {valid_node_ids}")

        try:
            # 读取junctions.geojson文件
            with open(junctions_geojson, "r", encoding="utf-8") as f:
                junctions_data = json.load(f)
        except FileNotFoundError:
            print("未找到junctions.geojson文件")
            return
        except Exception as e:
            print(f"读取junctions.geojson文件时出错: {e}")
            return

        ###判断节点是不是河流尽头，若是则也要进行删除###
        # 从max_part提取junction ID
        max_junction_id = int(max_part.split(".")[0])
        print(f"最大流域ID对应的junction点: {max_junction_id}")
        # 检查这个junction点控制的子流域是否均在ids_to_merge0中
        # 读取upstream_cells.geojson文件获取所有流域信息
        with open(upstream_cells_geojson, "r", encoding="utf-8") as f:
            upstream_data = json.load(f)

        # 查找指定junction节点控制的所有流域
        junction_controlled_watersheds = set()
        for feature in upstream_data["features"]:
            watershed_id = feature["properties"]["id"]
            # 检查流域ID是否由目标junction节点控制（以"junction_id."开头）
            if watershed_id.startswith(f"{max_junction_id}."):
                junction_controlled_watersheds.add(watershed_id)

        print(
            f"Junction {max_junction_id} 控制的子流域: {junction_controlled_watersheds}"
        )

        # 检查这些子流域是否都在ids_to_merge0中
        all_controlled_in_merge = all(
            f"Watershed{watershed_id}" in ids_to_merge0 or watershed_id in ids_to_merge0
            for watershed_id in junction_controlled_watersheds
        )
        if all_controlled_in_merge and junction_controlled_watersheds:
            print(f"Junction {max_junction_id} 控制的所有子流域都在删除列表中")

            # 利用downstream_dict0，查找这些子流域是否存在上游
            has_upstream = False
            for watershed_id in junction_controlled_watersheds:
                full_watershed_id = (
                    f"Watershed{watershed_id}"
                    if not watershed_id.startswith("Watershed")
                    else watershed_id
                )
                # 检查这个子流域是否在downstream_dict0中作为下游节点出现
                for upstream_id, downstream_id in downstream_dict.items():
                    if downstream_id == full_watershed_id:
                        print(f"子流域 {full_watershed_id} 存在上游流域 {upstream_id}")
                        has_upstream = True
                        break
                if has_upstream:
                    break

            # 如果这些子流域均不存在上游，则将这个junction点加入到valid_node_ids中
            if not has_upstream:
                print(
                    f"Junction {max_junction_id} 控制的子流域均无上游，将其加入删除列表"
                )
                if valid_node_ids and max_junction_id not in valid_node_ids:
                    valid_node_ids.append(max_junction_id)
            else:
                print(f"Junction {max_junction_id} 控制的子流域存在上游，按原逻辑处理")
        else:
            print(
                f"Junction {max_junction_id} 控制的子流域不全在删除列表中，按原逻辑处理"
            )

        # 过滤掉需要删除的junction特征
        filtered_junctions = []
        removed_junctions_count = 0

        for feature in junctions_data["features"]:
            props = feature.get("properties", {})
            junction_id = props.get("id")

            # 如果该junction的ID在删除列表中，则跳过(不添加到filtered_junctions)
            if junction_id in valid_node_ids:
                print(f"删除junction点: {junction_id}")
                removed_junctions_count += 1
            else:
                filtered_junctions.append(feature)

        # 更新features列表
        junctions_data["features"] = filtered_junctions

        # 保存修改后的文件
        try:
            with open(junctions_deleted_geojson, "w", encoding="utf-8") as f:
                json.dump(junctions_data, f, ensure_ascii=False, indent=2)
            print(f"成功删除{removed_junctions_count}个junction点，更新后的文件已保存")
        except Exception as e:
            print(f"保存junctions_merge.geojson文件时出错: {e}")
    else:
        # 读取junctions.geojson文件
        with open(junctions_geojson, "r", encoding="utf-8") as f:
            junctions_data = json.load(f)
        with open(junctions_deleted_geojson, "w", encoding="utf-8") as f:
            json.dump(junctions_data, f, ensure_ascii=False, indent=2)
        print("未提供valid_node_ids，跳过junction点删除操作")
    # 调用独立的处理函数处理source_deleted.geojson中的点
    process_source_deleted_points(
        source_deleted_geojson,
        ids_to_merge0,
        downstream_dict,
        fdir,
        identified_streams,
        flow_directions,
        grid,
    )


# 处理source_deleted.geojson中的点，根据删除的流域进行相应更新
def process_source_deleted_points(
    source_deleted_geojson,
    ids_to_delete,
    downstream_dict,
    fdir,
    identified_streams,
    flow_directions,
    grid,
):
    """
    处理source_deleted.geojson中的点，根据删除的流域进行相应更新

    参数:
    source_deleted_geojson: str, source_deleted点GeoJSON文件路径
    ids_to_delete: list, 需要删除的流域ID列表
    downstream_dict: dict, 下游关系字典
    fdir: array, 流向数组
    identified_streams: array, 河道网络数组
    flow_directions: dict, 流向映射字典
    grid: Grid, Grid对象

    返回:
    bool: 处理是否成功
    """

    # 读取source_deleted.geojson文件
    try:
        with open(source_deleted_geojson, "r", encoding="utf-8") as f:
            source_deleted_data = json.load(f)
    except FileNotFoundError:
        print(f"{source_deleted_geojson} 文件不存在，创建空文件")
        source_deleted_data = {"type": "FeatureCollection", "features": []}
        # 创建空文件
        with open(source_deleted_geojson, "w", encoding="utf-8") as f:
            json.dump(source_deleted_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"读取 {source_deleted_geojson} 文件时出错: {e}")
        return False

    # 1. 提取source_deleted.geojson中各点id
    source_deleted_features = source_deleted_data.get("features", [])
    source_deleted_ids = []
    source_deleted_features_dict = {}

    for feature in source_deleted_features:
        if feature["geometry"]["type"] == "Point":
            props = feature.get("properties", {})
            point_id = str(props.get("id", ""))
            source_deleted_ids.append(point_id)
            source_deleted_features_dict[point_id] = feature

    print(f"source_deleted.geojson 中的点ID: {source_deleted_ids}")

    # 2. 根据source_deleted.geojson中各点id，在downstream_dict中找到其下游，
    # 若其下游的点对应的Watershed在ids_to_delete中，则在source_deleted.geojson中删除对应的点
    features_to_remove = []

    for point_id in source_deleted_ids:
        # 在downstream_dict中查找该点的下游
        if point_id in downstream_dict:
            downstream_id = downstream_dict[point_id]
            # 构造完整的流域ID
            watershed_id = f"Watershed{downstream_id}"
            # 检查下游流域是否在删除列表中
            if watershed_id in ids_to_delete:
                features_to_remove.append(source_deleted_features_dict[point_id])
                print(
                    f"点 {point_id} 的下游流域 {watershed_id} 在删除列表中，将删除该点"
                )

    # 从features中移除需要删除的点
    for feature in features_to_remove:
        if feature in source_deleted_data["features"]:
            source_deleted_data["features"].remove(feature)

    # 更新source_deleted_ids和source_deleted_features_dict
    remaining_features = source_deleted_data["features"]
    source_deleted_ids = []
    source_deleted_features_dict = {}

    for feature in remaining_features:
        if feature["geometry"]["type"] == "Point":
            props = feature.get("properties", {})
            point_id = str(props.get("id", ""))
            source_deleted_ids.append(point_id)
            source_deleted_features_dict[point_id] = feature

    # 3. 根据source_deleted.geojson中各点id，提取出其数字位，
    # 若有两个点的数字位相同，则将这两个点合并为1个点
    # 提取数字位并分组
    id_groups = {}

    for point_id in source_deleted_ids:
        # 提取数字部分 (例如 "source_1.1" -> "1.1")
        if "_" in point_id:
            numeric_part = point_id.split("_", 1)[1]  # 获取下划线后的部分
        else:
            numeric_part = point_id

        # 按整数部分分组 (例如 "1.1" 和 "1.2" 都归为整数部分 "1")
        if "." in numeric_part:
            integer_part = numeric_part.split(".")[0]  # 获取小数点前的整数部分
        else:
            integer_part = numeric_part  # 如果没有小数点，整数部分就是全部数字

        if integer_part not in id_groups:
            id_groups[integer_part] = []
        id_groups[integer_part].append(point_id)

    print(f"按整数位分组的结果: {id_groups}")

    # 处理需要合并的点组
    for numeric_part, group_ids in id_groups.items():
        # 如果该组只有一个点，无需合并
        if len(group_ids) <= 1:
            continue

        print(f"发现需要合并的点组，数字位: {numeric_part}, 点ID: {group_ids}")

        # 找到数字位最小的点ID作为保留的ID
        # 按数字大小排序
        sorted_ids = sorted(
            group_ids,
            key=lambda x: [
                int(part) if part.isdigit() else part
                for part in (x.split("_", 1)[1] if "_" in x else x).split(".")
            ],
        )
        keep_id = sorted_ids[0]
        keep_feature = source_deleted_features_dict[keep_id]
        print(f"保留点ID: {keep_id}")

        # 移除其他点的特征
        for remove_id in group_ids:
            if remove_id != keep_id:
                feature_to_remove = source_deleted_features_dict[remove_id]
                if feature_to_remove in source_deleted_data["features"]:
                    source_deleted_data["features"].remove(feature_to_remove)

        # 如果需要更新保留点的位置信息（当下游点需要重新计算时）
        if len(group_ids) >= 2:
            # 获取保留点的行列坐标
            keep_props = keep_feature.get("properties", {})
            keep_row = keep_props.get("row")
            keep_col = keep_props.get("col")

            # 找到该点下游的第一个点的位置信息
            downstream_cell = find_downstream_cell(
                keep_row, keep_col, fdir, identified_streams, flow_directions
            )

            if downstream_cell:
                downstream_row, downstream_col = downstream_cell
                print(f"找到下游点坐标: row={downstream_row}, col={downstream_col}")

                # 将行列坐标转换为地理坐标
                try:
                    down_geo_x, down_geo_y = View.affine_transform(
                        grid.affine, downstream_col, downstream_row
                    )

                    # 更新保留点的信息到下游位置
                    keep_feature["geometry"]["coordinates"] = [
                        float(down_geo_x),
                        float(down_geo_y),
                    ]
                    keep_props["row"] = int(downstream_row)
                    keep_props["col"] = int(downstream_col)
                    print(f"已更新合并点的信息到下游位置")

                except Exception as e:
                    print(f"更新合并点信息时出错: {e}")
            else:
                print("未找到下游点")

        # 确保保留点的ID是数字位最小的那个点的ID
        keep_feature["properties"]["id"] = keep_id

    # 保存更新后的source_deleted.geojson文件
    try:
        with open(source_deleted_geojson, "w", encoding="utf-8") as f:
            json.dump(source_deleted_data, f, ensure_ascii=False, indent=2)
        print(f"已更新 {source_deleted_geojson} 文件")
        return True
    except Exception as e:
        print(f"保存 {source_deleted_geojson} 文件时出错: {e}")
        return False


# 为source_deleted.geojson中的每个点添加downstream_point属性
def add_downstream_point_to_source_deleted(downstream_dict, source_deleted_geojson):
    """
    为source_deleted.geojson中的每个点添加downstream_point属性

    参数:
    downstream_dict: dict, 包含上游点到下游点映射关系的字典
    source_deleted_geojson: str, source_deleted.geojson文件路径

    返回:
    bool: 操作是否成功
    """
    try:
        # 读取source_deleted.geojson文件
        with open(source_deleted_geojson, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 遍历所有特征，添加downstream_point属性
        for feature in data["features"]:
            if feature["geometry"]["type"] == "Point":
                # 获取当前点的ID
                current_id = feature["properties"].get("id", "")[
                    7:
                ]  # 去掉"source_"前缀

                # 在downstream_dict中查找下游点
                downstream_id = downstream_dict.get(current_id, None)

                # 添加downstream_point属性
                feature["properties"]["downstream_point"] = downstream_id

                if downstream_id:
                    print(f"为点 {current_id} 添加下游点: {downstream_id}")
                else:
                    print(f"点 {current_id} 未找到下游点")

        # 保存更新后的文件
        with open(source_deleted_geojson, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"成功为source_deleted.geojson中的点添加downstream_point属性")
        return True

    except FileNotFoundError:
        print(f"未找到文件: {source_deleted_geojson}")
        return False
    except Exception as e:
        print(f"处理source_deleted.geojson时出错: {e}")
        return False


####   8.根据river_network_linestrings_merge.geojson生成河段首尾坐标   ####
def extract_river_network_info(
    break_point_geojson, river_network_linestrings, dem, junctions_geojson, grid
):
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
        with open(break_point_geojson, "r", encoding="utf-8") as f:
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


# -----------------------------------------------------------------------------------------------------------------------------
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
# 合并/删除流域
# 合并流域
def perform_watershed_merge(
    ids_to_merge,
    identified_streams,
    grid,
    fdir,
    flow_directions,
    inflated_dem,
    break_point,
    sub_catchment_merge,
    upstream_cells_merge,
    junctions_merge,
    river_network_linestrings_merge,
    downstream_dict_merge,
    random_folder_name,
    plan_name,
):
    """
    执行流域合并操作并生成可视化结果

    参数:
    ids_to_merge: list, 需要合并的流域ID列表
    downstream_dict: dict, 浹域间的下游关系字典
    identified_streams: array, 河道网络数组
    grid: Grid, Grid对象
    fdir: array, 流向数组
    flow_directions: dict, 流向映射字典
    inflated_dem: array, 填洼后的DEM数据

    返回:
    dict: 包含处理结果信息的字典
    """

    (
        sub_catchment_merge,
        upstream_cells_merge,
        junctions_merge,
        river_network_linestrings_merge,
        downstream_dict_merge,
    ) = _resolve_merge_output_paths(
        random_folder_name,
        plan_name,
        sub_catchment_merge,
        upstream_cells_merge,
        junctions_merge,
        river_network_linestrings_merge,
        downstream_dict_merge,
    )

    # 根据是否进行合并\删除操作，选择调用的geojson文件
    _, _, junctions, _, _, downstream_dict_v = set_geojson_file_paths(
        random_folder_name, plan_name, chuangjian=False
    )
    # 验证所选流域是否可以合并
    validated_ids0, valid_junction_ids0 = validate_catchment_merge(
        ids_to_merge,
        downstream_dict_v,
        junctions,
    )
    # 创建merge.geojson文件
    (
        sub_catchment,
        upstream_cells,
        junctions,
        river_network_linestrings,
        source_deleted,
        downstream_dict_v,
    ) = set_geojson_file_paths(random_folder_name, plan_name)
    # 合并流域，生成合并合并后的流域边界
    merged_polygons = merge_subcatchments_by_id(sub_catchment, validated_ids0)

    # 重新生成流域边界
    process_merged_catchment(
        sub_catchment, sub_catchment_merge, validated_ids0, merged_polygons
    )

    # 重新生成junction点和流域出口点
    remove_upstream_and_junctions_after_merge(
        upstream_cells,
        upstream_cells_merge,
        junctions,
        junctions_merge,
        validated_ids0,
        downstream_dict_v,
        fdir,
        identified_streams,
        flow_directions,
        grid,
        valid_junction_ids0,
    )

    # 重新生成河段LineString
    generate_river_network_linestrings(
        junctions_merge,
        break_point,
        upstream_cells_merge,
        river_network_linestrings_merge,
        identified_streams,
        grid,
        fdir,
        flow_directions,
    )

    add_river_length_to_geojson(river_network_linestrings_merge)

    # 重新生成拓扑结构
    downstream_dict0 = build_upstream_downstream_relationships(
        break_point,
        upstream_cells_merge,
        source_deleted,
        identified_streams,
        grid,
        fdir,
        flow_directions,
        downstream_dict_merge,
    )

    print(f"\nupstream点之间的下游关系字典: {downstream_dict0}")

    # 生成河段首尾坐标
    river_info = extract_river_network_info(
        break_point, river_network_linestrings_merge, inflated_dem, junctions, grid
    )

    # 打印结果
    print("河段信息:")
    for riv_id, info in river_info.items():
        print(
            f"'{riv_id}': {{\"length_km\": {info['length_km']}, \"From_point\": {info['From_point']}, \"To_point\": {info['To_point']}}}"
        )
    # 返回处理结果
    return downstream_dict0, river_info


def perform_watershed_deletion(
    ids_to_delete,
    identified_streams,
    grid,
    fdir,
    flow_directions,
    inflated_dem,
    break_point,
    sub_catchment_merge,
    upstream_cells_merge,
    junctions_merge,
    river_network_linestrings_merge,
    downstream_dict_merge,
    random_folder_name,
    plan_name,
):
    """
    执行流域删除操作并生成可视化结果

    参数:
    ids_to_delete: list, 需要删除的流域ID列表
    downstream_dict: dict, 流域间的下游关系字典
    identified_streams: array, 河道网络数组
    grid: Grid, Grid对象
    fdir: array, 流向数组
    flow_directions: dict, 流向映射字典
    inflated_dem: array, 填洼后的DEM数据

    返回:
    dict: 包含处理结果信息的字典
    """

    (
        sub_catchment_merge,
        upstream_cells_merge,
        junctions_merge,
        river_network_linestrings_merge,
        downstream_dict_merge,
    ) = _resolve_merge_output_paths(
        random_folder_name,
        plan_name,
        sub_catchment_merge,
        upstream_cells_merge,
        junctions_merge,
        river_network_linestrings_merge,
        downstream_dict_merge,
    )

    # 验证所选流域是否可以删除
    (
        sub_catchment,
        upstream_cells,
        junctions,
        river_network_linestrings,
        source_deleted,
        downstream_dict_v,
    ) = set_geojson_file_paths(random_folder_name, plan_name, chuangjian=False)
    validated_groups, valid_junction_ids = validate_catchment_delete(
        ids_to_delete, downstream_dict_v, junctions
    )

    # 对每个验证通过的组进行处理
    for i, group_ids in enumerate(validated_groups):
        print(f"处理第 {i + 1} 组流域: {group_ids}")
        if len(validated_groups) == 1:
            group_ids = [group_ids]
        (
            sub_catchment,
            upstream_cells,
            junctions,
            river_network_linestrings,
            source_deleted,
            downstream_dict_v,
        ) = set_geojson_file_paths(random_folder_name, plan_name)
        if isinstance(group_ids[0], list):
            group_ids = [item for sublist in group_ids for item in sublist]
        # 重新生成流域边界
        process_deleted_catchment(sub_catchment, sub_catchment_merge, group_ids)

        # 重新生成删除后的upstream_and_junctions并生成source_deleted.geojson文件
        remove_upstream_and_junctions_after_delete(
            upstream_cells,
            upstream_cells_merge,
            junctions,
            junctions_merge,
            source_deleted,
            group_ids,
            downstream_dict_v,
            fdir,
            identified_streams,
            flow_directions,
            grid,
            valid_junction_ids,
        )

        # 为source_deleted.geojson中的每个点添加downstream_point属性
        add_downstream_point_to_source_deleted(
            downstream_dict_v, source_deleted
        )  # 用的downstream_dict为删除前的

        # 重新生成拓扑结构
        downstream_dict0 = build_upstream_downstream_relationships(
            break_point,
            upstream_cells_merge,
            source_deleted,
            identified_streams,
            grid,
            fdir,
            flow_directions,
            downstream_dict_merge,
        )
        print(f"\nupstream点之间的下游关系字典: {downstream_dict0}")

        move_files_to_output_ori(random_folder_name, plan_name)

    # 使用最后一组处理后的文件生成河段LineString
    generate_river_network_linestrings(
        junctions,
        break_point,
        upstream_cells,
        river_network_linestrings_merge,
        identified_streams,
        grid,
        fdir,
        flow_directions,
    )

    add_river_length_to_geojson(river_network_linestrings_merge)

    # 生成河段首尾坐标
    river_info = extract_river_network_info(
        break_point, river_network_linestrings_merge, inflated_dem, junctions, grid
    )

    # 打印结果
    print("河段信息:")
    for riv_id, info in river_info.items():
        print(
            f"'{riv_id}': {{\"length_km\": {info['length_km']}, \"From_point\": {info['From_point']}, \"To_point\": {info['To_point']}}}"
        )

    return validated_groups, downstream_dict0, river_info


# -----------------------------------------------------------------------------------------------------------------------------
# 将生成的文件移动到目录
def move_files_to_output_ori(random_folder_name, plan_name):
    """
    将生成的文件移动到 output_ori 目录
    """
    # 确保目标目录存在，若不存在则自动创建
    # plan_name = "方案1"

    target_path1 = "basic_file"
    target_directory1 = os.path.join(random_folder_name, plan_name, target_path1)
    os.makedirs(target_directory1, exist_ok=True)

    files_merge_to_move = [
        "sub_catchment_merge.geojson",
        "upstream_cells_merge.geojson",
        "junctions_merge.geojson",
        "river_network_linestrings_merge.geojson",
        "source_deleted.geojson",
        "downstream_dict_merge.json",
    ]

    # 移动每个文件
    for file_name1 in files_merge_to_move:
        target_path = os.path.join(target_directory1, file_name1)
        if os.path.exists(target_path):
            print(f"{file_name1} already exists in {target_directory1}")
        elif os.path.exists(file_name1):
            source_path = file_name1
            shutil.move(source_path, target_path)
            print(f"已移动 {file_name1} 到 {target_directory1}")
        else:
            print(f"File {file_name1} does not exist")
    return random_folder_name


def unmerge_files(random_folder_name, plan_name):

    basic_file = "basic_file"
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
        "source_deleted.geojson"
    ]

    # 创建预报方案1目录，与target_directory同级
    target_directory = os.path.join(random_folder_name, plan_name, "basic_file")
    os.makedirs(target_directory, exist_ok=True)
    source_directory = os.path.join(random_folder_name, "output_ori", "basic_file")
    # 先将文件复制到预报方案1目录
    for file_name in files_to_move:
        source_path = os.path.join(source_directory, file_name)
        if os.path.exists(source_path):
            target_path = os.path.join(target_directory, file_name)
            shutil.copy2(source_path, target_path)  # 使用copy2保留文件元数据
            print(f"已复制 {file_name} 到 {target_path}")
        else:
            print(f"文件 {source_path} 不存在，无法复制")

    outputs = {
        "junctions": parse_geojson_to_frontend(os.path.join(target_directory, "junctions.geojson"),
                                               entity_type="point"),
        # "upstream_cells_merge": os.path.join(output_dir1, "upstream_cells_merge.geojson"),
        "reaches": parse_geojson_to_frontend(os.path.join(target_directory, "river_network_linestrings.geojson"),
                                             entity_type="line"),
        # "downstream_dict_merge.json": os.path.join(output_dir1, "downstream_dict_merge.json"),
        "subWatersheds": parse_geojson_to_frontend(
            os.path.join(target_directory, "sub_catchment.geojson"), entity_type="polygon"
        ),
        "point":parse_geojson_to_frontend(os.path.join(target_directory, "point.geojson"),
                                               entity_type="point"),
        # "source_deleted.geojson": os.path.join(output_dir1, "source_deleted.geojson"),
        "prePath": random_folder_name,
    }
    return outputs


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
        if feature['properties']['id'] == 1:
            # 复制feature避免修改原数据
            new_feature = feature.copy()
            # 获取原id并添加前缀
            original_id = new_feature['properties']['id']
            new_feature['properties']['id'] = f"break_point_{original_id}"
            merged_data['features'].append(new_feature)

    # 写入合并后的数据到新文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    print(f"成功合并文件，输出到: {output_file}")
    return output_file



# -----------------------------------------------------------------------------------------------------------------------------


class Merge_delete:
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
        control_points=None,
        random_folder_name="0000",
        plan_name="方案1",
        state_dir="temp_state",
    ):
        """Initialize the MPC service"""

        delete_geojson_files(mode="all")
        target_path = "basic_file"
        os.makedirs(
            os.path.join(random_folder_name, plan_name, target_path), exist_ok=True
        )
        os.makedirs(os.path.join(random_folder_name, state_dir), exist_ok=True)

        # 特殊文件路径20251205

        target_directory00 = os.path.join(random_folder_name, "output_ori", target_path)
        self.break_point_geojson = os.path.join(
            target_directory00, "break_point.geojson"
        )

        self.state_dir = os.path.join(random_folder_name, state_dir)
        self.plan_name = plan_name
        self.random_folder_name = random_folder_name
        self.start_time = time.time()
        if control_points and len(control_points) > 0:
            first_point = control_points[0]
            self.xy = (first_point[0], first_point[1])  # 使用第一个控制点的坐标
        else:
            with open(
                os.path.join(target_directory00, "break_point.geojson"),
                "r",
                encoding="utf-8",
            ) as f:
                break_point_data = json.load(f)
            # 查找 id 为 1 的点
            for feature in break_point_data.get("features", []):
                if feature.get("properties", {}).get("id") == 1:
                    # 获取坐标
                    coordinates = feature["geometry"]["coordinates"]
                    # 将坐标赋值给 xy (注意 GeoJSON 坐标是 [longitude, latitude] 格式)
                    self.xy = (coordinates[0], coordinates[1])
                    print(f"从 break_point.geojson 中读取坐标: {self.xy}")
                    break
                else:
                    # 如果没有找到 id 为 1 的点，则使用传入的 xy 参数或默认值
                    self.xy = xy
                    print(
                        "未在 break_point.geojson 中找到 id 为 1 的点，使用传入的 xy 参数或默认值"
                    )

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
        self.cell_size_x = 30
        self.cell_size_y = 30
        self.merged_operation = False
        self.deleted_operation = False
        self.tif_path = os.path.join(self.state_dir, "inflated_dem.tif")
        self.identified_streams_path = os.path.join(
            self.state_dir, "identified_streams.tif"
        )
        # 初始化控制点
        self.control_points = control_points if control_points is not None else []

    def step4_merge_or_delete_watersheds(self, operation, watershed_ids):
        """
        Step 4: Merge/delete watersheds and regenerate river topology structure

        Parameters:
        operation (str): Either "merge" or "delete"
        watershed_ids (list): List of watershed IDs to merge or delete

        Returns:
        dict: Operation results
        """

        print(
            f"Step 4: {operation.capitalize()}ing watersheds and regenerating topology..."
        )
        x, y = self.xy
        # 加载相关变量
        grid, inflated_dem, fdir, acc = load_grid_and_recompute(x, y, self.tif_path)

        grid1 = Grid.from_raster(self.identified_streams_path)
        identified_streams = grid1.read_raster(self.identified_streams_path)

        # 特殊文件路径20260105，因为系统用不到删除流域的功能，所以这里就不处理了

        # target_path1 = "output_merge"
        # target_directory1 = os.path.join(self.random_folder_name, self.plan_name, target_path1)
        # river_network_linestrings_merge_geojson = os.path.join(target_directory1, 'river_network_linestrings_merge.geojson')

        if operation == "merge":
            self.merged_operation = True
            print(f"Merging watersheds: {watershed_ids}")
            # Use existing function for merging
            self.downstream_dict, self.river_info = perform_watershed_merge(
                watershed_ids,
                identified_streams,
                grid,
                fdir,
                self.flow_directions,
                inflated_dem,
                self.break_point_geojson,
                "sub_catchment_merge.geojson",
                "upstream_cells_merge.geojson",
                "junctions_merge.geojson",
                "river_network_linestrings_merge.geojson",
                "downstream_dict_merge.json",
                self.random_folder_name,
                self.plan_name,
            )

        elif operation == "delete":
            self.deleted_operation = True
            print(f"Deleting watersheds: {watershed_ids}")
            # Use existing function for deleting
            result = perform_watershed_deletion(
                watershed_ids,
                identified_streams,
                grid,
                fdir,
                self.flow_directions,
                inflated_dem,
                self.break_point_geojson,
                "sub_catchment_merge.geojson",
                "upstream_cells_merge.geojson",
                "junctions_merge.geojson",
                "river_network_linestrings_merge.geojson",
                "downstream_dict_merge.json",
                self.random_folder_name,
                self.plan_name,
            )
            validated_groups, self.downstream_dict, self.river_info = result
        else:
            raise ValueError("Operation must be either 'merge' or 'delete'")

        print("River network topology regeneration completed.")
        print("Step 4 completed.")
        return {
            "status": f"watersheds {operation}d",
            "operation": operation,
            "ids": watershed_ids,
        }

    def generate_final_outputs(self):
        """
        Final output generation based on whether merge/delete operations were performed

        Returns:
        dict: Information about generated output files
        """
        print("Generating final outputs...")

        # 生成point.geojson文件
        (
            sub_catchment,
            upstream_cells,
            junctions,
            river_network_linestrings,
            source_deleted,
            downstream_dict_v,
        ) = set_geojson_file_paths(self.random_folder_name, self.plan_name)

        output_dir1 = os.path.join(
            self.random_folder_name, self.plan_name, "basic_file"
        )
        merge_point_geojson(junctions, self.break_point_geojson, os.path.join(output_dir1, "point.geojson"))

        # 将生成的文件移动到目录
        move_files_to_output_ori(self.random_folder_name, self.plan_name)

        # Outputs after merge/delete operations
        # outputs = {
        #     "junctions_merge.geojson": os.path.join(
        #         output_dir1, "junctions_merge.geojson"
        #     ),
        #     "upstream_cells_merge.geojson": os.path.join(
        #         output_dir1, "upstream_cells_merge.geojson"
        #     ),
        #     "river_network_linestrings_merge.geojson": os.path.join(
        #         output_dir1, "river_network_linestrings_merge.geojson"
        #     ),
        #     "downstream_dict_merge.json": os.path.join(
        #         output_dir1, "downstream_dict_merge.json"
        #     ),
        #     "sub_catchment_merge.geojson": os.path.join(
        #         output_dir1, "sub_catchment_merge.geojson"
        #     ),
        #     "source_deleted.geojson": os.path.join(
        #         output_dir1, "source_deleted.geojson"
        #     ),
        # }
        # Outputs after merge/delete operations
        # outputs = {
        #     "junctions_merge.geojson": os.path.join(output_dir1, "junctions_merge.geojson"),
        #     "upstream_cells_merge.geojson": os.path.join(output_dir1, "upstream_cells_merge.geojson"),
        #     "river_network_linestrings_merge.geojson": os.path.join(output_dir1, "river_network_linestrings_merge.geojson"),
        #     "downstream_dict_merge.json": os.path.join(output_dir1, "downstream_dict_merge.json"),
        #     "sub_catchment_merge.geojson": os.path.join(output_dir1, "sub_catchment_merge.geojson"),
        #     "source_deleted.geojson": os.path.join(output_dir1, "source_deleted.geojson"),
        # }
        outputs = {
            "junctions": parse_geojson_to_frontend(os.path.join(output_dir1, "junctions_merge.geojson"), entity_type="point"),
            # "upstream_cells_merge": os.path.join(output_dir1, "upstream_cells_merge.geojson"),
            "reaches": parse_geojson_to_frontend( os.path.join(output_dir1, "river_network_linestrings_merge.geojson"), entity_type="line"),
            # "downstream_dict_merge.json": os.path.join(output_dir1, "downstream_dict_merge.json"),
            "subWatersheds": parse_geojson_to_frontend(
                os.path.join(output_dir1, "sub_catchment_merge.geojson"), entity_type="polygon"
            ),
            # "source_deleted.geojson": os.path.join(output_dir1, "source_deleted.geojson"),
            "prePath": self.random_folder_name,
        }
        print("Generated outputs:")
        # for file, description in outputs.items():
        #     print(f"  - {file}: {description}")

        end_time = time.time()
        execution_time = end_time - self.start_time
        print(f"Total execution time: {execution_time:.2f} seconds")

        return outputs


#
# # dem_filename = "E:\DEMshuju\ASTGTMV003_N28E118_dem.tif"
# # shapefile_path = "E:\pysheds-master\Watershed1.2.shp"   # 用户输入流域shp
# dem_filename = r"E:\pysheds-master\规划云平台数据\流域生成测试栅格\basin_tif.tif"
# shapefile_path = None
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
# service = MPCWatershedService(
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
# # # 用户定义的流域合并或删除
# # id_to_delete = ['Watershed3.1', 'Watershed2.2']
# # # 5. 执行第四步：删除流域（可选）
# # delete_result = service.step4_merge_or_delete_watersheds(
# #     operation="delete",
# #     watershed_ids=id_to_delete
# # )
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
