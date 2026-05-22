#!/usr/bin/env python
# -*- coding: utf-8 -*-


from pysheds.grid import Grid
import seaborn as sns
import json
import numpy as np
from pysheds.sview import View
import warnings
import time
import os


warnings.filterwarnings("ignore")
sns.set_palette("pastel")
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


####   4.生成河道拓扑关系   ####
# 读取upstream_cells.geojson文件并构建upstream点之间的下游关系字典
def build_upstream_downstream_relationships(
    break_point_geojson,
    junction_geojson,
    upstream_geojson,
    source_deleted_geojson,
    junction_id,
    identified_streams,
    grid,
    fdir,
    flow_directions,
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

        # 创建一个位置索引 (row, col) -> [point_types_list]，用于处理坐标重合的情况
        upstream_positions = {}

        # 添加upstream点到位置索引
        for feature in upstream_data["features"]:
            if feature["geometry"]["type"] == "Point":
                props = feature["properties"]
                upstream_id = props["id"]
                row = props["row"]
                col = props["col"]
                position_key = (row, col)

                # 如果该位置已经有其他点，则添加到列表中；否则新建列表
                if position_key in upstream_positions:
                    if isinstance(upstream_positions[position_key], list):
                        # 如果已经是列表，添加新点（避免重复）
                        if upstream_id not in upstream_positions[position_key]:
                            upstream_positions[position_key].append(upstream_id)
                    else:
                        # 如果是字符串，转换为列表
                        existing_id = upstream_positions[position_key]
                        upstream_positions[position_key] = [existing_id, upstream_id]
                else:
                    upstream_positions[position_key] = [upstream_id]

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
                    position_key = (row, col)

                    # 添加break point到相应位置
                    if position_key in upstream_positions:
                        if isinstance(upstream_positions[position_key], list):
                            # 如果已经是列表，添加新点（避免重复）
                            if "break_point_1" not in upstream_positions[position_key]:
                                upstream_positions[position_key].append("break_point_1")
                        else:
                            # 如果是字符串，转换为列表
                            existing_id = upstream_positions[position_key]
                            upstream_positions[position_key] = [
                                existing_id,
                                "break_point_1",
                            ]
                    else:
                        upstream_positions[position_key] = ["break_point_1"]
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
                    position_key = (row, col)

                    # 添加source deleted点到相应位置
                    if position_key in upstream_positions:
                        if isinstance(upstream_positions[position_key], list):
                            # 如果已经是列表，添加新点（避免重复）
                            if (
                                source_deleted_id
                                not in upstream_positions[position_key]
                            ):
                                upstream_positions[position_key].append(
                                    source_deleted_id
                                )
                        else:
                            # 如果是字符串，转换为列表
                            existing_id = upstream_positions[position_key]
                            upstream_positions[position_key] = [
                                existing_id,
                                source_deleted_id,
                            ]
                    else:
                        upstream_positions[position_key] = [source_deleted_id]
                    print(
                        f"添加source deleted点 (id={source_deleted_id})到位置: row={row}, col={col}"
                    )

        # 为每个upstream点查找其下游的upstream点
        all_features_to_process = upstream_data["features"][:]
        # 如果有source_deleted数据，也添加到处理队列中
        if source_deleted_data:
            all_features_to_process.extend(source_deleted_data["features"])

        # 读取junction.geojson文件
        junction_data = None
        try:
            with open(junction_geojson, "r", encoding="utf-8") as f:
                junction_data = json.load(f)
        except FileNotFoundError:
            print("未找到junction.geojson文件")

        # 如果存在junction.geojson文件，将其中id为junction_id的点也加入索引
        if junction_data:
            for feature in junction_data["features"]:
                if (
                    feature["geometry"]["type"] == "Point"
                    and feature["properties"].get("id") == junction_id
                ):
                    # 获取junction点的行列坐标
                    row = feature["properties"]["row"]
                    col = feature["properties"]["col"]
                    position_key = (row, col)

                    # 添加junction点到相应位置
                    junction_identifier = f"junction_{junction_id}"
                    if position_key in upstream_positions:
                        if isinstance(upstream_positions[position_key], list):
                            # 如果已经是列表，添加新点（避免重复）
                            if (
                                junction_identifier
                                not in upstream_positions[position_key]
                            ):
                                upstream_positions[position_key].append(
                                    junction_identifier
                                )
                        else:
                            # 如果是字符串，转换为列表
                            existing_id = upstream_positions[position_key]
                            upstream_positions[position_key] = [
                                existing_id,
                                junction_identifier,
                            ]
                    else:
                        upstream_positions[position_key] = [junction_identifier]
                    print(
                        f"添加junction点 (id={junction_id})到位置: row={row}, col={col}"
                    )
                    break

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

                    # 在build_upstream_downstream_relationships函数中，需要在遍历开始前检查起始点是否有重合点
                    if (current_row, current_col) in upstream_positions:
                        # 检查起始点是否有重合的点
                        start_position_info = upstream_positions[(current_row, current_col)]
                        print(f"起始点有重合点: row={current_row}, col={current_col},{start_position_info}")

                        # 确保start_position_info是列表
                        if not isinstance(start_position_info, list):
                            start_position_info = [start_position_info]

                        # 分离非junction点和junction点
                        non_junction_points = []
                        junction_point = None

                        for point_type in start_position_info:
                            if not point_type.startswith("junction_"):
                                non_junction_points.append(point_type)
                            elif point_type.startswith("junction_"):
                                junction_point = point_type
                        print(junction_point, non_junction_points)
                        # 如果起始点同时存在非junction点和junction点，则非junction点是上游，junction点是下游
                        if junction_point and non_junction_points:
                            # 将所有非junction点连接到junction点
                            downstream_dict[non_junction_points[0]] = junction_point
                            print(f"将非junction点 {non_junction_points} 连接到 junction点 {junction_point}，，，{downstream_dict}")
                            break



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

                    # 检查下一个点是否是upstream点或break point或source deleted点或junction点
                    if (next_row, next_col) in upstream_positions:
                        downstream_position_info = upstream_positions[
                            (next_row, next_col)
                        ]

                        # 确保downstream_position_info是列表
                        if not isinstance(downstream_position_info, list):
                            downstream_position_info = [downstream_position_info]

                        # 优先选择非junction点作为下游连接
                        downstream_upstream_id = None
                        junction_point = None
                        print("downstream_position_info:", downstream_position_info)

                        # 分离非junction点和junction点
                        non_junction_points = []
                        for point_type in downstream_position_info:
                            if not point_type.startswith("junction_"):
                                non_junction_points.append(point_type)
                            elif point_type.startswith("junction_"):
                                junction_point = point_type

                        # 如果存在非junction点和junction点在同一位置，则非junction点是上游，junction点是下游
                        if junction_point and non_junction_points:
                            # 将当前的upstream_id连接到非junction点
                            # 将非junction点连接到junction点
                            for non_junction_point in non_junction_points:
                                downstream_dict[non_junction_point] = junction_point
                            # 当前upstream_id连接到非junction点
                            downstream_upstream_id = non_junction_points[0]
                        elif non_junction_points:
                            # 只有非junction点，则选择第一个
                            downstream_upstream_id = non_junction_points[0]
                        elif junction_point:
                            # 只有junction点，则选择它
                            downstream_upstream_id = junction_point
                        # else:
                        #     # 如果仍然没找到合适的点，使用第一个
                        #     if len(downstream_position_info) > 0:
                        #         downstream_upstream_id = downstream_position_info[0]

                        if downstream_upstream_id is not None:
                            downstream_dict[upstream_id] = downstream_upstream_id
                            found_downstream = True
                            # if downstream_upstream_id == 'break_point_1':
                            #     print(f"upstream点 {upstream_id} 找到下游break point (id=1)")
                            # else:
                            #     print(f"upstream点 {upstream_id} 找到下游upstream点 {downstream_upstream_id}")
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

    return downstream_dict


# 读取upstream_cells.geojson文件并构建upstream点之间的下游关系字典
def build_evolution_paths_relationships(
    break_point_geojson,
    junction_geojson,
    source_deleted_geojson,
    identified_streams,
    grid,
    fdir,
    flow_directions,
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

        # 读取junction.geojson文件
        junction_data = None
        try:
            with open(junction_geojson, "r", encoding="utf-8") as f:
                junction_data = json.load(f)
        except FileNotFoundError:
            print("未找到junction.geojson文件")

        # 如果存在junction.geojson文件，将其中所有junction点加入索引
        if junction_data:
            for feature in junction_data[
                "features"
            ]:  # 注意这里改为遍历junction_data而不是upstream_data
                if feature["geometry"]["type"] == "Point":
                    # 获取junction点的ID和行列坐标
                    junc_id = feature["properties"].get("id")
                    row = feature["properties"]["row"]
                    col = feature["properties"]["col"]
                    # 使用特殊ID标识junction点
                    upstream_positions[(row, col)] = junc_id
                    print(f"添加junction点 (id={junc_id})到位置: row={row}, col={col}")

        # 为每个upstream点查找其下游的upstream点
        all_features_to_process = junction_data["features"]
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

    return downstream_dict


# 读取upstream_cells.geojson文件并构建upstream点之间的下游关系字典
def build_upstream_downstream_relationships_bp(
    break_point_geojson,
    upstream_geojson,
    source_deleted_geojson,
    identified_streams,
    grid,
    fdir,
    flow_directions,
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

    return downstream_dict


# 根据是否合并\删除，设置所有geojson文件路径
def set_geojson_file_paths(random_folder_name):
    """
    根据sub_catchment_merge.geojson是否存在来设置所有geojson文件路径
    """
    # 确保目标目录存在，若不存在则自动创建
    # 检索random_folder_name文件夹下所有包含basic_file子文件夹的路径
    target_directories = []

    # 遍历random_folder_name下的所有子文件夹
    for item in os.listdir(random_folder_name):
        item_path = os.path.join(random_folder_name, item)
        # 检查是否是文件夹且包含basic_file子文件夹
        if os.path.isdir(item_path):
            basic_file_path = os.path.join(item_path, "basic_file")
            if os.path.exists(basic_file_path) and os.path.isdir(basic_file_path):
                target_directories.append(basic_file_path)

    # 如果找到了包含basic_file的文件夹，遍历处理每个路径
    results = []
    for target_directory in target_directories:

        parent_directory = os.path.dirname(target_directory)
        output_directory = os.path.join(parent_directory, "clibrate")
        os.makedirs(output_directory, exist_ok=True)

        # 检查sub_catchment_merge.geojson是否存在
        use_merged_files = os.path.exists(
            os.path.join(target_directory, "sub_catchment_merge.geojson")
        )
        if use_merged_files:
            print("检测到合并后的文件，使用合并后的geojson文件")
            sub_catchment = os.path.join(
                target_directory, "sub_catchment_merge.geojson"
            )
            upstream_cells = os.path.join(
                target_directory, "upstream_cells_merge.geojson"
            )
            junctions = os.path.join(target_directory, "junctions_merge.geojson")
            river_network_linestrings = os.path.join(
                target_directory, "river_network_linestrings_merge.geojson"
            )
            source_deleted = os.path.join(target_directory, "source_deleted.geojson")
            # 从JSON文件中读取downstream_dict0
            try:
                with open(
                    os.path.join(target_directory, "downstream_dict_merge.json"),
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
            source_deleted = os.path.join(target_directory, "source_deleted.geojson")
            try:
                with open(
                    os.path.join(target_directory, "downstream_dict.json"),
                    "r",
                    encoding="utf-8",
                ) as f:
                    downstream_dict_v = json.load(f)
            except Exception as e:
                print(f"读取downstream_dict.json文件时出错: {e}")
                downstream_dict_v = {}

        results.append(
            (
                sub_catchment,
                upstream_cells,
                junctions,
                river_network_linestrings,
                source_deleted,
                downstream_dict_v,
                output_directory,
            )
        )

    # 如果只有一个结果，直接返回该结果
    if len(results) == 1:
        return results[0]
    else:
        # 如果有多个结果，可以选择返回第一个或者返回所有结果
        print(f"找到 {len(results)} 个包含basic_file的文件夹")
        return results  # 返回所有结果


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
def filter_downstream_dict_for_junction(downstream_dict, junction_id):
    """
    筛选出指定junction的所有上游流域ID，并只保留下游关系字典中与该junction相关的部分

    参数:
    downstream_dict : dict
        完整的下游关系字典
    junction_id : str or int
        目标junction的ID

    返回:
    dict : 筛选后的下游关系字典
    """
    target_junction = f"junction_{junction_id}"

    # 第一步：找出所有直接或间接指向目标junction的上游流域ID
    upstream_ids = set()

    # 遍历下游关系字典，找出所有最终会流向目标junction的流域
    for upstream_id, downstream_id in downstream_dict.items():
        if downstream_id == target_junction:
            upstream_ids.add(upstream_id)

    # 继续查找这些上游流域的更多上游流域（递归查找）
    changed = True
    while changed:
        changed = False
        for upstream_id, downstream_id in downstream_dict.items():
            if downstream_id in upstream_ids and upstream_id not in upstream_ids:
                upstream_ids.add(upstream_id)
                changed = True

    # 添加junction本身到结果中
    upstream_ids.add(target_junction)

    # 第二步：构建筛选后的字典
    filtered_dict = {}
    for upstream_id, downstream_id in downstream_dict.items():
        # 如果上游ID在我们的目标集合中，则保留这个关系
        if upstream_id in upstream_ids:
            filtered_dict[upstream_id] = downstream_id

    return filtered_dict


class Junction_downstream_dict:
    """
    junction点以上的河道拓扑结构
    """

    def __init__(self, random_folder_name, state_dir="./temp_state"):
        """Initialize the MPC service"""
        self.state_dir = os.path.join(random_folder_name, state_dir)
        os.makedirs(state_dir, exist_ok=True)
        # 特殊文件路径20251205
        target_path = "basic_file"
        target_directory = os.path.join(random_folder_name, "output_ori", target_path)
        self.break_point_geojson = os.path.join(target_directory, "break_point.geojson")

        self.random_folder_name = random_folder_name
        self.all_downstream_dicts = {}
        self.start_time = time.time()
        self.downstream_dict = {}
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
        self.tif_path = os.path.join(self.state_dir, "inflated_dem.tif")
        self.identified_streams_path = os.path.join(
            self.state_dir, "identified_streams.tif"
        )

    # junction点的上游upstream点拓扑结构
    def generate_downstream_dict(self):
        # 调用函数获取结果
        results = set_geojson_file_paths(self.random_folder_name)

        # 确保结果是列表格式（无论是一个还是多个）
        if not isinstance(results, list):
            results = [results]

        # 统一循环处理每个结果
        for idx, (
            sub_catchment,
            upstream_cells,
            junctions,
            river_network_linestrings,
            source_deleted_geojson,
            downstream_dict_v,
            target_directory,
        ) in enumerate(results):
            print(f"处理第 {idx + 1} 个文件夹: {target_directory}")

            with open(self.break_point_geojson, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 查找id为1的点
            for feature in data.get("features", []):
                if (
                    feature.get("geometry", {}).get("type") == "Point"
                    and feature.get("properties", {}).get("id") == 1
                ):
                    coords = feature["geometry"]["coordinates"]
                    x, y = coords[0], coords[1]

            grid, inflated_dem, fdir, acc = load_grid_and_recompute(x, y, self.tif_path)

            grid1 = Grid.from_raster(self.identified_streams_path)
            identified_streams = grid1.read_raster(self.identified_streams_path)

            # 提取所有junction点
            junction_ids = []
            with open(junctions, "r", encoding="utf-8") as f:
                junction_data = json.load(f)

            # 提取所有ID
            for feature in junction_data.get("features", []):
                if feature.get("geometry", {}).get("type") == "Point":
                    junction_id = feature.get("properties", {}).get("id")
                    if junction_id is not None:
                        junction_ids.append(junction_id)
            # 存储所有junction拓扑结构的字典
            all_downstream_dicts = {}

            # break_point_1生成拓扑结构,储存all_downstream_dicts字典中
            downstream_dict1 = build_upstream_downstream_relationships_bp(
                self.break_point_geojson,
                upstream_cells,
                source_deleted_geojson,
                identified_streams,
                grid,
                fdir,
                self.flow_directions,
            )
            all_downstream_dicts["break_point_1"] = downstream_dict1

            # 为每个junction生成拓扑结构
            for junction_id in junction_ids:
                print(f"正在处理 junction_id: {junction_id}")
                try:
                    downstream_dict = build_upstream_downstream_relationships(
                        self.break_point_geojson,
                        junctions,
                        upstream_cells,
                        source_deleted_geojson,
                        junction_id,
                        identified_streams,
                        grid,
                        fdir,
                        self.flow_directions,
                    )
                    # 生成特定junction的下游关系字典
                    filtered_result = filter_downstream_dict_for_junction(
                        downstream_dict, junction_id
                    )
                    all_downstream_dicts[str(junction_id)] = filtered_result
                    print(f"junction_id {junction_id} 的拓扑结构已生成")
                except Exception as e:
                    print(f"处理 junction_id {junction_id} 时出错: {e}")

            self.all_downstream_dicts = all_downstream_dicts

            # 确保字典中的所有键值都可以被JSON序列化
            serializable_dict = {}
            for key, value in all_downstream_dicts.items():
                if hasattr(key, "item"):
                    serializable_key = key.item()
                else:
                    serializable_key = key

                if isinstance(value, dict):
                    serializable_value = {}
                    for k, v in value.items():
                        if hasattr(k, "item"):
                            k = k.item()
                        if hasattr(v, "item"):
                            v = v.item()
                        serializable_value[str(k)] = str(v)
                else:
                    serializable_value = value

                serializable_dict[str(serializable_key)] = serializable_value

            all_downstream_dicts_path = os.path.join(
                target_directory, "all_downstream_dicts.json"
            )
            with open(all_downstream_dicts_path, "w", encoding="utf-8") as f:
                json.dump(serializable_dict, f, ensure_ascii=False, indent=2)
            print(f"all_downstream_dicts已保存到: {all_downstream_dicts_path}")

        print("Sub-watershed generation completed.")

    # 从拓扑结构字典中提取每个junction的完整上游流域名称（包含所有层级）
    def extract_watershed_names_complete(self):
        """
        从拓扑结构字典中提取每个junction的完整上游流域名称（包含所有层级）

        返回:
        dict : 格式为 {'1': {'Watershed1.1', 'Watershed1.2', ...}, '2': {...}, ...}
        """
        # 调用函数获取结果
        results = set_geojson_file_paths(self.random_folder_name)

        # 确保结果是列表格式（无论是一个还是多个）
        if not isinstance(results, list):
            results = [results]

        # 统一循环处理每个结果
        for idx, (
            sub_catchment,
            upstream_cells,
            junctions,
            river_network_linestrings,
            source_deleted_geojson,
            downstream_dict_v,
            target_directory,
        ) in enumerate(results):
            print(f"处理第 {idx + 1} 个文件夹: {target_directory}")

            result = {}

            # 从文件中读取all_downstream_dicts
            all_downstream_dicts_path = os.path.join(
                target_directory, "all_downstream_dicts.json"
            )
            try:
                with open(all_downstream_dicts_path, "r", encoding="utf-8") as f:
                    all_downstream_dicts = json.load(f)
            except FileNotFoundError:
                print(f"文件 {all_downstream_dicts_path} 不存在")
                continue
            except json.JSONDecodeError:
                print(f"文件 {all_downstream_dicts_path} 格式错误")

            # 处理每个junction的拓扑结构
            for junction_key, downstream_dict in all_downstream_dicts.items():
                # print(f"正在处理 junction_key: {junction_key}")
                watershed_names = set()

                # 收集所有不包含"junction"的上游ID
                for upstream_id, downstream_id in downstream_dict.items():
                    # print(f"正在处理 upstream_id: {upstream_id}")
                    # print(f"正在处理 downstream_id: {downstream_id}")

                    # 跳过包含"junction"的条目和以"source_"开头的条目
                    if "junction" in str(upstream_id) or str(upstream_id).startswith(
                        "source_"
                    ):
                        continue

                    # 特别处理break_point1的情况
                    if junction_key == "break_point_1":
                        # 对于break_point1，直接添加所有上游ID（除了break_point_1本身）
                        if upstream_id != "break_point_1":
                            watershed_names.add(f"Watershed{upstream_id}")
                        # 显式添加Watershed1（对应break_point_1）
                        if downstream_id == "break_point_1":
                            watershed_names.add("Watershed1")
                    else:
                        # 处理普通junction的情况
                        # 处理break_point_1，转换为Watershed1
                        if upstream_id == "break_point_1":
                            watershed_names.add("Watershed1")
                        elif downstream_id == "break_point_1":
                            # 当下游是break_point_1时，也需要将上游节点转换命名
                            watershed_names.add(f"Watershed{upstream_id}")
                        else:
                            watershed_names.add(f"Watershed{upstream_id}")

                # 对watershed_names进行排序后转换为列表
                sorted_watershed_names = sorted(list(watershed_names))
                result[junction_key] = sorted_watershed_names
            print(result)
            # 检查result是否为空，如果为空则设置默认结果
            if result == {'break_point_1': []}:
                result = {'break_point_1': ['Watershed1']}
                print("检测到result为空，设置默认结果: {'break_point_1': ['Watershed1']}")

            # 保存watershed_names到JSON文件
            watershed_names_path = os.path.join(
                target_directory, "watershed_names.json"
            )

            # 将set转换为list以便JSON序列化
            serializable_result = {}
            for key, value in result.items():
                serializable_result[str(key)] = list(value)

            with open(watershed_names_path, "w", encoding="utf-8") as f:
                json.dump(serializable_result, f, ensure_ascii=False, indent=2)
            print(f"watershed_names已保存到: {watershed_names_path}")

    # 生成所有junction的拓扑结构字典
    def evolution_paths_relationships(self):

        # 调用函数获取结果
        results = set_geojson_file_paths(self.random_folder_name)

        # 确保结果是列表格式（无论是一个还是多个）
        if not isinstance(results, list):
            results = [results]

        # 统一循环处理每个结果
        for idx, (
            sub_catchment,
            upstream_cells,
            junctions,
            river_network_linestrings,
            source_deleted_geojson,
            downstream_dict_v,
            target_directory,
        ) in enumerate(results):
            print(f"处理第 {idx + 1} 个文件夹: {target_directory}")

            with open(self.break_point_geojson, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 查找id为1的点
            for feature in data.get("features", []):
                if (
                    feature.get("geometry", {}).get("type") == "Point"
                    and feature.get("properties", {}).get("id") == 1
                ):
                    coords = feature["geometry"]["coordinates"]
                    x, y = coords[0], coords[1]

            grid, inflated_dem, fdir, acc = load_grid_and_recompute(x, y, self.tif_path)

            grid1 = Grid.from_raster(self.identified_streams_path)
            identified_streams = grid1.read_raster(self.identified_streams_path)

            downstream_relations = build_evolution_paths_relationships(
                self.break_point_geojson,
                junctions,
                source_deleted_geojson,
                identified_streams,
                grid,
                fdir,
                self.flow_directions,
            )

            complete_paths = {}
            # 特殊处理：添加终点节点（没有下游的节点）的空路径
            downstream_only_nodes = set(downstream_relations.values()) - set(
                downstream_relations.keys()
            )
            for node in downstream_only_nodes:
                if node not in complete_paths:
                    complete_paths[node] = []
            # 为每个节点构建完整下游路径
            for node in downstream_relations.keys():
                path = []
                current = node

                # 追踪到最下游的完整路径
                visited = set()  # 防止循环
                while current in downstream_relations and current not in visited:
                    visited.add(current)
                    next_node = downstream_relations[current]
                    path.append(next_node)
                    current = next_node

                complete_paths[node] = path

            evolution_paths = complete_paths

            # 检查evolution_paths是否为空，如果为空则设置默认结果
            if not evolution_paths or len(evolution_paths) == 0:
                evolution_paths = {'break_point_1': []}
                print("检测到evolution_paths为空，设置默认结果: {'break_point_1': []}")


            # 保存evolution_paths到JSON文件
            evolution_paths_path = os.path.join(
                target_directory, "evolution_paths.json"
            )
            # 确保字典中的所有键值都可以被JSON序列化
            serializable_evolution_paths = {}
            for key, value in evolution_paths.items():
                serializable_key = (
                    str(key) if not isinstance(key, (str, int, float, bool)) else key
                )
                serializable_value = []
                for item in value:
                    serializable_item = (
                        str(item)
                        if not isinstance(item, (str, int, float, bool))
                        else item
                    )
                    serializable_value.append(serializable_item)
                serializable_evolution_paths[serializable_key] = serializable_value

            with open(evolution_paths_path, "w", encoding="utf-8") as f:
                json.dump(serializable_evolution_paths, f, ensure_ascii=False, indent=2)
            print(f"evolution_paths已保存到: {evolution_paths_path}")

    # 从river_network_linestrings_merge.geojson文件中提取河流连接关系
    def extract_river_connections(self):
        """
        从river_network_linestrings_merge.geojson文件中提取河流连接关系

        参数:
        geojson_path : str
            geojson文件路径

        返回:
        dict : 格式为 {(from_junction, to_junction): riv_id}
        """

        # 调用函数获取结果
        results = set_geojson_file_paths(self.random_folder_name)

        # 确保结果是列表格式（无论是一个还是多个）
        if not isinstance(results, list):
            results = [results]

        # 统一循环处理每个结果
        for idx, (
            sub_catchment,
            upstream_cells,
            junctions,
            river_network_linestrings,
            source_deleted_geojson,
            downstream_dict_v,
            target_directory,
        ) in enumerate(results):
            print(f"处理第 {idx + 1} 个文件夹: {target_directory}")

            # 读取geojson文件
            with open(river_network_linestrings, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 构建musk_params字典
            musk_params = {}

            # 特殊处理break_point_1
            break_point_key = "break_point_1"  # 在字典中使用break_point1作为键

            # 遍历所有特征
            for feature in data.get("features", []):
                properties = feature.get("properties", {})

                from_point = properties.get("From_point")
                to_point = properties.get("To_point")
                riv_id = properties.get("Riv-ID")

                if from_point and to_point and riv_id:
                    # 解析from_point和to_point中的数字部分
                    # 处理junction_数字格式
                    if from_point.startswith("junction_"):
                        from_num = int(from_point.split("_")[1])
                    elif from_point == "break_point_1":
                        from_num = break_point_key
                    else:
                        from_num = from_point

                    if to_point.startswith("junction_"):
                        to_num = int(to_point.split("_")[1])
                    elif to_point == "break_point_1":
                        to_num = break_point_key
                    else:
                        to_num = to_point

                    # 添加到字典中，使用元组作为键
                    musk_params[(from_num, to_num)] = riv_id

            # 保存musk_params到JSON文件
            river_connections_path = os.path.join(target_directory, "musk_params.json")

            # 转换元组键为字符串键以便JSON序列化，使用元组字符串格式
            serializable_musk_params = {}
            for (from_key, to_key), riv_id in musk_params.items():
                # 使用Python元组字符串格式
                string_key = f"({from_key}, {to_key})"
                serializable_musk_params[string_key] = riv_id

            with open(river_connections_path, "w", encoding="utf-8") as f:
                json.dump(serializable_musk_params, f, ensure_ascii=False, indent=2)
            print(f"river_connections已保存到: {river_connections_path}")


# # 创建实例
# junction_analyzer = Junction_downstream_dict(
#     random_folder_name="d0dd0fc7-57a3-4132-8542-9f78ddb5d61e",
#     plan_name="方案2",
#     state_dir="./temp_state"
# )
#
# try:
#     # 生成下游关系字典
#     downstream_dict = junction_analyzer.generate_downstream_dict()
#     watershed_names = junction_analyzer.extract_watershed_names_complete()
#     evolution_paths = junction_analyzer.evolution_paths_relationships()
#     musk_params = junction_analyzer.extract_river_connections()
#     print("下游关系字典生成成功:")
#     print(musk_params)
# except Exception as e:
#     print(f"生成下游关系字典时出错: {e}")
