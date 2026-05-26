from pysheds.grid import Grid
import glob
import os
import json
import numpy as np
import geopandas as gpd
from pysheds.sview import View
from rasterio import features
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
import re
import tempfile
import rasterio


# 鎶婄偣鍧愭爣鍒楄〃杞垚 break_point.geojson 鍚屾鏍煎紡鐨?GeoJSON
def points_to_geojson(points, output_path=None, point_type="break_point"):
    """
    鎶婅嫢骞茬偣鍧愭爣杞垚 GeoJSON FeatureCollection锛堜笌 break_point.geojson 鍚屾鏍煎紡锛夈€?
    姣忎釜鐐规寜杈撳叆椤哄簭鑷姩璧?id锛?, 2, 3, ...锛夈€?

    鍙傛暟:
    points: 鐐瑰潗鏍囧垪琛ㄣ€傛瘡涓厓绱犲彲浠ユ槸:
            - (x, y) 鍏冪粍/鍒楄〃
            - {"x": ..., "y": ...} 瀛楀吀
    output_path: 鍙€夈€傝嫢鎻愪緵鍒欏悓鏃跺啓鍏ヨ鏂囦欢璺緞銆?
    point_type: 鍐欏叆 properties.type 瀛楁鐨勫€硷紝榛樿 "break_point"

    杩斿洖:
    dict: GeoJSON FeatureCollection 瀛楀吀

    绀轰緥:
        >>> points_to_geojson([(105.20, 27.06), (105.08, 27.06)], "out.geojson")
        {'type': 'FeatureCollection', 'features': [...]}
    """
    features = []
    for i, pt in enumerate(points, start=1):
        if isinstance(pt, dict):
            x, y = float(pt["x"]), float(pt["y"])
        else:
            x, y = float(pt[0]), float(pt[1])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [x, y]},
            "properties": {"id": i, "type": point_type},
        })

    geojson = {"type": "FeatureCollection", "features": features}

    if output_path is not None:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False)

    return geojson


# 璁＄畻娴佸煙闈㈢Н
def calculate_catchment_area(grid_data, cell_size_x=30, cell_size_y=30, unit='km2'):
    """
    璁＄畻娴佸煙闈㈢Н锛堝亣璁炬爡鏍煎ぇ灏忎负30*30绫筹級

    鍙傛暟:
    grid_data: 鏍呮牸鏁版嵁锛坣umpy鏁扮粍锛夛紝娴佸煙鍖哄煙鍊煎簲涓?锛屽叾浠栧尯鍩熶负0鎴朜aN
    unit: 闈㈢Н鍗曚綅锛?m2' 琛ㄧず骞虫柟绫筹紝'km2' 琛ㄧず骞虫柟鍏噷锛?ha' 琛ㄧず鍏》

    杩斿洖:
    area: 娴佸煙闈㈢Н
    """
    # 鑾峰彇鏈夋晥鍍忓厓鏁伴噺锛堥潪闆跺儚鍏冿級
    valid_cells = np.sum(grid_data > 0)

    # 鍗曚釜鍍忓厓闈㈢Н锛堝钩鏂圭背锛?
    cell_area_m2 = cell_size_x * cell_size_y  # 30绫?* 30绫?= 900骞虫柟绫?

    # 璁＄畻鎬婚潰绉紙骞虫柟绫筹級
    total_area_m2 = valid_cells * cell_area_m2

    # 鏍规嵁鎸囧畾鍗曚綅杞崲
    if unit == 'km2':
        area = total_area_m2 / 1000000  # 杞崲涓哄钩鏂瑰叕閲?
    elif unit == 'ha':
        area = total_area_m2 / 10000  # 杞崲涓哄叕椤?
    elif unit == 'm2':
        area = total_area_m2  # 淇濇寔骞虫柟绫?
    else:
        raise ValueError("鍗曚綅蹇呴』鏄?'m2', 'km2', 鎴?'ha'")

    return area
# 鑾峰彇娴佸煙涓績鐐?
def find_raster_centroid_fast(grid_data, grid):
    """
    蹇€熻绠楁爡鏍间腑蹇冪偣

    鍙傛暟:
    grid_data: 鏍呮牸鏁版嵁锛坣umpy鏁扮粍锛?

    杩斿洖:
    centroid_row, centroid_col: 涓績鐐圭殑琛屽垪鍧愭爣
    """
    # 鑾峰彇鎵€鏈夋湁鏁堝儚鍏冪殑鍧愭爣
    valid_rows, valid_cols = np.where(grid_data > 0)

    # 鐩存帴璁＄畻骞冲潎鍊硷紙浣跨敤鍐呯疆鍑芥暟锛屾晥鐜囨渶楂橈級
    centroid_row = np.mean(valid_rows)
    centroid_col = np.mean(valid_cols)
    # 灏嗚鍒楀潗鏍囪浆鎹负鍦扮悊鍧愭爣锛堢粡绾害锛?
    x, y = grid.affine * (centroid_col, centroid_row)

    return x, y
# 鎻愬彇娴佸煙杈圭晫杞负polygon
def create_polygon_from_raster(area_data, grid_obj, catchment_id):
    """
    浣跨敤rasterio浠庢爡鏍兼暟鎹垱寤哄杈瑰舰
    """
    # 纭繚鏁版嵁鏄簩鍊煎寲鐨剈int8绫诲瀷
    area_data = np.where(area_data > 0, 1, 0).astype(np.uint8)

    # 鍒涘缓涓存椂GeoTIFF鏂囦欢
    with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as tmp_file:
        temp_filename = tmp_file.name

    try:
        # 鑾峰彇浠垮皠鍙樻崲鐭╅樀
        if hasattr(grid_obj, 'affine'):
            transform = grid_obj.affine
        elif hasattr(grid_obj, 'viewfinder') and hasattr(grid_obj.viewfinder, 'affine'):
            transform = grid_obj.viewfinder.affine
        else:
            # 鍒涘缓榛樿鐨勪豢灏勫彉鎹㈢煩闃?
            transform = rasterio.transform.from_bounds(
                0, 0, area_data.shape[1], area_data.shape[0],
                area_data.shape[1], area_data.shape[0]
            )

        # 浣跨敤rasterio鍒涘缓GeoTIFF鏂囦欢
        with rasterio.open(
                temp_filename, 'w',
                driver='GTiff',
                height=area_data.shape[0],
                width=area_data.shape[1],
                count=1,
                dtype=np.uint8,
                transform=transform,
                crs='EPSG:4326'  # 璁剧疆鍧愭爣绯伙紝鏍规嵁瀹為檯鎯呭喌璋冩暣
        ) as dst:
            dst.write(area_data, 1)

        # 浣跨敤rasterio璇诲彇骞跺鐞?
        with rasterio.open(temp_filename) as src:
            data = src.read(1)
            transform = src.transform

            # 鍒涘缓mask锛屽€煎ぇ浜?鐨勫儚鍏冧负鏈夋晥
            mask = (data > 0)

            # 鐢熸垚褰㈢姸锛屽皾璇曚笉鍚岀殑connectivity鍙傛暟
            shapes_gen = features.shapes(data, mask=mask, transform=transform, connectivity=8)

            # 鎻愬彇鎵€鏈夋湁鏁堝杈瑰舰
            polygons = []
            for geom, value in shapes_gen:
                if value > 0:
                    # 浣跨敤 shape 鍑芥暟浠嶨eoJSON瀛楀吀鍒涘缓澶氳竟褰?
                    shapely_poly = shape(geom)
                    polygons.append(shapely_poly)

            return polygons

    except Exception as e:
        print(f"鍒涘缓澶氳竟褰㈡椂鍑洪敊: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        # 娓呯悊涓存椂鏂囦欢
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)
# 涓篵reak_point.geojson鍜寀pstream_cells.geojson涓殑鎵€鏈夌偣鐢熸垚娴佸煙
def generate_catchments_for_all_points(point_geojson, grid, fdir, acc, dirmap, snap_threshold=2000):
    """
    涓?point_geojson 涓殑鎵€鏈夌偣鐢熸垚娴佸煙銆?
    姣忎釜鐐瑰厛鐢?snap_to_mask 璐村埌绱Н娴?> snap_threshold 鐨勬渶杩戞渤閬撴爡鏍间笂锛?
    閬垮厤鐢ㄦ埛杈撳叆鐨勫潗鏍囧亸绂讳富娌抽亾瀵艰嚧娴佸煙鎻愬彇閿欒銆?

    鍙傛暟:
    point_geojson: 鍊炬郴鐐?GeoJSON 鏂囦欢璺緞
    grid: pysheds Grid 瀵硅薄
    fdir: 娴佸悜鏁扮粍
    acc: 绱Н娴佹暟缁?
    dirmap: D8 娴佸悜缂栫爜
    snap_threshold: 绱Н娴侀槇鍊硷紝> 璇ュ€肩殑鏍呮牸瑙嗕负"涓绘渤閬?
    """


    # 瀛樺偍鎵€鏈夐渶瑕佺敓鎴愭祦鍩熺殑鐐?
    all_points = []
    # 璇诲彇break_point.geojson涓殑鐐?
    try:
        with open(point_geojson, 'r', encoding='utf-8') as f:
            break_point_data = json.load(f)

        for feature in break_point_data['features']:
            if feature['geometry']['type'] == 'Point':
                coords = feature['geometry']['coordinates']
                point_id = feature['properties']['id']
                all_points.append({
                    'x': coords[0],
                    'y': coords[1],
                    'id': f'break_point_{point_id}'
                })
    except Exception as e:
        print(f"璇诲彇point.geojson鏃跺嚭閿? {e}")

    # 娌抽亾鎺╄啘锛氱疮绉祦澶т簬闃堝€肩殑鏍呮牸
    river_mask = acc > snap_threshold

    # 涓烘瘡涓偣鐢熸垚娴佸煙
    catchments = {}
    for point in all_points:
        try:
            # 灏嗗€炬郴鐐硅创鍒版渶杩戠殑涓绘渤閬撴爡鏍?
            snapped = grid.snap_to_mask(river_mask, (point['x'], point['y']))
            snapped = np.atleast_2d(np.asarray(snapped))
            x_snap, y_snap = float(snapped[0, 0]), float(snapped[0, 1])
            print(f"  鐐?{point['id']} snap: ({point['x']}, {point['y']}) -> ({x_snap}, {y_snap})")

            # 鐢?snap 鍚庣殑鍧愭爣鐢熸垚娴佸煙
            catch = grid.catchment(
                x=x_snap,
                y=y_snap,
                fdir=fdir,
                dirmap=dirmap,
                xytype='coordinate'
            )
            if np.sum(catch > 0) == 0:
                print(
                    f"warning: point {point['id']} produced an empty catchment; "
                    "check snap_threshold or whether the point falls within the DEM extent"
                )
            catchments[point['id']] = catch
            print(f"generated catchment for point {point['id']} (snap x={x_snap}, y={y_snap})")

        except Exception as e:
            print(f"failed to generate catchment for point {point['id']}: {e}")
            print(f"涓虹偣 {point['id']} 鐢熸垚娴佸煙鏃跺嚭閿? {e}")

    return catchments
# 娴佸煙鐩稿噺
def compute_unique_areas(all_catchments):
    """
    鎸夌収娴佸煙缂栧彿鍊掑簭璁＄畻姣忎釜娴佸煙鐨勭嫭鏈夊尯鍩?

    绠楁硶閫昏緫锛?
    1. 鎸夋祦鍩熺殑缂栧彿鍊掑簭璁＄畻锛屽洜涓轰笅娓告祦鍩熻偗瀹氭病鏈夋敮娴侊紝灏变笉鐢ㄨ繘琛岃绠?
    2. 姣斿璇翠笂娓告祦鍩熷氨鍑忓幓涓嬫父娴佸煙
    3. 鎸夐『搴忚繘琛岃绠楃嫭鏈夊尯鍩?

    Parameters:
    all_catchments: dict
        鍖呭惈鎵€鏈夋祦鍩熸爡鏍肩殑瀛楀吀锛岄敭涓烘祦鍩烮D锛屽€间负Raster瀵硅薄

    Returns:
    dict
        姣忎釜娴佸煙鐙湁鐨勫尯鍩?
    """
    # 鑾峰彇鎵€鏈夋祦鍩烮D
    catchment_ids = list(all_catchments.keys())

    # 鎸夌収娴佸煙缂栧彿杩涜鎺掑簭
    # 鍋囪娴佸煙ID鏍煎紡涓烘暟瀛?鏁板瓧鎴栨暟瀛?鏁板瓧_new鐨勫舰寮?
    def extract_sort_key(catchment_id):
        # 鎻愬彇ID涓殑涓荤紪鍙峰拰娆＄紪鍙风敤浜庢帓搴?
        import re
        # 鍖归厤鏍煎紡濡?"break_point_1.1", "upstream_9-2", "8-1_new" 绛?
        match = re.search(r'(\d+)[\-\.](\d+)', catchment_id)
        if match:
            # 杩斿洖涓荤紪鍙峰拰娆＄紪鍙风殑鍏冪粍锛岀敤浜庢帓搴?
            return (int(match.group(1)), int(match.group(2)))
        else:
            # 濡傛灉娌℃湁鍖归厤鍒扮壒瀹氭牸寮忥紝灏濊瘯鎻愬彇绗竴涓暟瀛?
            match = re.search(r'(\d+)', catchment_id)
            return (int(match.group(1)), 0) if match else (0, 0)

    # 鎸夌収缂栧彿鍊掑簭鎺掑垪
    sorted_catchment_ids = sorted(catchment_ids, key=extract_sort_key, reverse=True)

    print("澶勭悊椤哄簭:", sorted_catchment_ids)  # 鐢ㄤ簬璋冭瘯锛屽彲浠ョ湅鍒板疄闄呯殑澶勭悊椤哄簭

    unique_areas = {}
    processed_areas = {}  # 瀛樺偍宸茬粡澶勭悊杩囩殑娴佸煙鐙湁鍖哄煙

    # 鎸夊€掑簭澶勭悊姣忎釜娴佸煙
    for catchment_id in sorted_catchment_ids:
        current_catchment = all_catchments[catchment_id]

        # 鍒濆鍖栧綋鍓嶆祦鍩熶负鍏ㄦ祦鍩?
        unique_area = np.where(current_catchment > 0, 1, 0).astype(np.uint8)

        # 鍑忓幓鎵€鏈夊凡缁忓鐞嗚繃鐨勪笅娓告祦鍩熷尯鍩?
        for processed_id, processed_area in processed_areas.items():
            # 浠庡綋鍓嶆祦鍩熶腑鍑忓幓宸插鐞嗘祦鍩熺殑鐙湁鍖哄煙
            unique_area = np.where(
                (unique_area > 0) & (processed_area > 0),
                0,  # 閲嶅彔鍖哄煙缃负0
                unique_area  # 闈為噸鍙犲尯鍩熶繚鎸佷笉鍙?
            )

        # 淇濆瓨褰撳墠娴佸煙鐨勭嫭鏈夊尯鍩?
        unique_areas[catchment_id] = unique_area
        processed_areas[catchment_id] = unique_area

    return unique_areas

# 鐢熸垚geojson鏂囦欢
def save_all_catchments_to_single_geojson(unique_areas, grid_obj, cell_size_x=30, cell_size_y=30,
                                          filename="sub_catchment.geojson"):
    """
    灏嗘墍鏈夊瓙娴佸煙淇濆瓨涓轰竴涓狦eoJSON鏂囦欢锛屼娇鐢ㄧ湡瀹炵殑DEM鍒嗚鲸鐜囪绠楅潰绉?

    鍙傛暟:
    unique_areas: 鎵€鏈夋祦鍩熺殑鏍呮牸鏁版嵁瀛楀吀
    grid_obj: pysheds Grid瀵硅薄
    filename: 杈撳嚭鏂囦欢鍚?
    """
    all_features = []

    # 涓烘瘡涓祦鍩熷垱寤篏eoJSON鐗瑰緛
    for catchment_id, area_data in unique_areas.items():
        print(f"\n澶勭悊娴佸煙: {catchment_id}")
        print(f"  鏈夋晥鍍忓厓鏁? {np.sum(area_data > 0)}")
        print(f"  鏁版嵁鑼冨洿: {area_data.min()} 鍒?{area_data.max()}")
        print(f"  鏁版嵁绫诲瀷: {area_data.dtype}")
        print(f"  鏁版嵁褰㈢姸: {area_data.shape}")
        try:
            # 浣跨敤rasterio鏂规硶鍒涘缓澶氳竟褰?
            polygons = create_polygon_from_raster(area_data, grid_obj, catchment_id)

            if not polygons:
                print(f"warning: no valid polygon generated for catchment {catchment_id}")
                print(f"area_data summary: unique={np.unique(area_data)}, total={np.sum(area_data)}")
                continue

            # 澶勭悊绗竴涓杈瑰舰锛堥€氬父涔熸槸鍞竴涓€涓級
            polygon = polygons[0]
            # 璁＄畻鏈夋晥鍍忓厓鏁伴噺(鍙敤浜庨獙璇侀潰绉?
            valid_cells = np.sum(area_data > 0)
            # 浣跨敤find_raster_centroid_fast鍑芥暟璁＄畻涓績鐐?
            centroid_x, centroid_y = find_raster_centroid_fast(area_data, grid_obj)
            # 璁＄畻闈㈢Н
            area_km2 = calculate_catchment_area(area_data, cell_size_x, cell_size_y, unit='km2')

            # 鑾峰彇澶栫幆鍧愭爣
            try:
                exterior_coords = list(polygon.exterior.coords)
                # 妫€鏌ュ潗鏍囨暟閲?
                if len(exterior_coords) < 4:
                    print(f"  璀﹀憡锛氭祦鍩?{catchment_id} 鐨勫杈瑰舰鍧愭爣鐐硅繃灏?({len(exterior_coords)} 涓偣)")
                    # 瀵逛簬鏋佸皬鐨勫尯鍩燂紝鍙兘闇€瑕佺壒娈婂鐞?
                    if len(exterior_coords) < 3:
                        print(f"skip catchment {catchment_id}: not enough coordinates")
                        continue

                # 纭繚澶氳竟褰㈤棴鍚?
                if exterior_coords[0] != exterior_coords[-1]:
                    exterior_coords.append(exterior_coords[0])
                    print("fixed polygon ring closure")

                # 楠岃瘉鍧愭爣鏈夋晥鎬?
                valid_coords = True
                for i, coord in enumerate(exterior_coords):
                    if not (isinstance(coord[0], (int, float)) and isinstance(coord[1], (int, float))):
                        print(f"  璀﹀憡: 娴佸煙 {catchment_id} 鍖呭惈鏃犳晥鍧愭爣 {i}: {coord}")
                        valid_coords = False
                        break

                if not valid_coords:
                    continue

            except Exception as e:
                print(f"  澶勭悊澶栫幆鍧愭爣鏃跺嚭閿? {e}")
                continue
            # 鍒涘缓GeoJSON鐗瑰緛
            # 鎻愬彇catchment_id涓殑鏁板瓧閮ㄥ垎锛堝寘鎷皬鏁扮偣锛?

            numeric_part = re.search(r'\d+(?:\.\d+)?', catchment_id)
            watershed_id = "Watershed" + numeric_part.group() if numeric_part else "Watershed" + catchment_id

            # 鍒涘缓GeoJSON鐗瑰緛
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [exterior_coords]
                },
                "properties": {
                    "id": watershed_id,
                    "area_km2": round(area_km2, 3),
                    "valid_cells": int(valid_cells),
                    "centroid_x": round(centroid_x, 6),
                    "centroid_y": round(centroid_y, 6)
                }
            }
            all_features.append(feature)

        except Exception as e:
            print(f"  澶勭悊娴佸煙 {catchment_id} 鏃跺嚭閿? {e}")
            continue

    # 鍒涘缓GeoJSON瀵硅薄
    geojson_data = {
        "type": "FeatureCollection",
        "features": all_features
    }

    # 淇濆瓨鍒版枃浠?
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    print(f"\n宸蹭繚瀛樻墍鏈夊瓙娴佸煙鍒癎eoJSON鏂囦欢: {filename}")
    print(f"saved {len(all_features)} catchment features")

    # 鎵撳嵃姣忎釜娴佸煙鐨勬憳瑕佷俊鎭?
    for feature in all_features:
        props = feature["properties"]
        print(f"  catchment id={props['id']}, area={props['area_km2']} km2, centroid=({props['centroid_x']}, {props['centroid_y']})")

    return filename

def process_watershed_analysis(point_geojson, dem_filename, dirmap,
                                snap_threshold=2000,
                                output_filename="sub_catchment.geojson"):
    """
    澶勭悊瀹屾暣鐨勬祦鍩熷垎鏋愭祦绋嬶細璇诲彇 DEM 鈫?濉醇 鈫?娴佸悜 鈫?绱Н娴?鈫?snap 鈫?catchment 鈫?GeoJSON

    鍙傛暟:
    point_geojson: 鍊炬郴鐐?GeoJSON 鏂囦欢璺緞
    dem_filename: DEM 鏍呮牸鏂囦欢璺緞
    dirmap: D8 娴佸悜缂栫爜锛坧ysheds 椤哄簭锛?
    snap_threshold: snap 鍒版渤閬撴椂鐨勭疮绉祦闃堝€笺€傛爡鏍肩疮绉祦 > 璇ュ€兼墠瑙嗕负"涓绘渤閬?锛?
                    鍊炬郴鐐逛細璐村埌鏈€杩戠殑杩欐牱涓€涓爡鏍笺€傞粯璁?2000锛堜腑绛変互涓婃渤閬擄級锛?
                    鐢ㄦ埛鍙寜 DEM 瀹為檯鎯呭喌璋冩暣銆?
    output_filename: 杈撳嚭 GeoJSON 璺緞銆侳lask 绛夋湇鍔″寲璋冪敤寤鸿浼犵粷瀵硅矾寰勬垨涓存椂鐩綍璺緞锛?
                     閬垮厤骞跺彂璇锋眰浜掔浉瑕嗙洊銆?

    杩斿洖:
    str: 杈撳嚭 GeoJSON 鏂囦欢璺緞
    """
    grid = Grid.from_raster(dem_filename)
    dem = grid.read_raster(dem_filename)

    # 濉醇 / 鍑归櫡 / 骞冲湴
    pit_filled_dem = grid.fill_pits(dem)
    flooded_dem = grid.fill_depressions(pit_filled_dem)
    inflated_dem = grid.resolve_flats(flooded_dem)

    # D8 娴佸悜
    fdir = grid.flowdir(inflated_dem, dirmap=dirmap)
    # 绱Н娴侊紙鐢ㄤ簬 snap 鍊炬郴鐐瑰埌涓绘渤閬擄級
    acc = grid.accumulation(fdir, dirmap=dirmap)

    # 鐢熸垚鎵€鏈?catchment锛堝唴閮ㄤ細鍏?snap 鍐嶆彁鍙栵級
    all_catchments = generate_catchments_for_all_points(
        point_geojson, grid, fdir, acc, dirmap, snap_threshold=snap_threshold
    )
    # 璁＄畻姣忎釜娴佸煙鐨勭嫭鏈夊尯鍩?
    unique_areas = compute_unique_areas(all_catchments)
    # 淇濆瓨娴佸煙杈圭晫鍒?GeoJSON
    save_all_catchments_to_single_geojson(
        unique_areas, grid, cell_size_x=30, cell_size_y=30,
        filename=output_filename,
    )

    return output_filename
