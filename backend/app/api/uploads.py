"""前端文件上传 API。

这个模块只做一件事：把浏览器上传的文件保存到后端本地目录，并返回 ArcPy
后续可以直接使用的绝对路径。项目当前不接数据库，所以不会保存文件记录表。

为什么需要上传接口：
    浏览器出于安全限制，不能可靠地把用户电脑上的完整绝对路径传给后端。
    因此前端应先上传文件，后端把文件保存到 `UPLOAD_FOLDER`，再把保存后的路径
    填入 `/api/render` 请求体。
"""

from __future__ import annotations

import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.utils.responses import error_response, success_response


uploads_bp = Blueprint("uploads", __name__)


# kind 是前端告诉后端“这个文件准备当什么用”。
# 后端会根据 kind 决定允许哪些文件后缀，避免把 Excel 当流域边界、把 aprx 当站点表使用。
ALLOWED_KINDS = {
    "basin_boundary",
    "river_network",
    "station_excel",
    "template_project",
}

# 每类业务文件允许的后缀。
# 流域边界和河流水系可以是单文件 geojson/kml，也可以是 shapefile zip，
# 也可以由前端一次多选 shp/shx/dbf/prj 等组件文件后用 files 字段上传。
ALLOWED_SUFFIXES_BY_KIND = {
    "basin_boundary": {".geojson", ".json", ".kml", ".zip", ".shp"},
    "river_network": {".geojson", ".json", ".kml", ".zip", ".shp"},
    "station_excel": {".xlsx"},
    "template_project": {".aprx"},
}

# Shapefile 必须一起选择的核心组件；.prj/.cpg 等是可选辅助文件。
REQUIRED_SHAPEFILE_COMPONENTS = {".shp", ".shx", ".dbf"}
ALLOWED_SHAPEFILE_COMPONENTS = {
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
    ".xml",
}


@uploads_bp.post("")
def upload_file():
    """保存一个上传文件，并返回可用于渲染请求的路径。"""
    # multipart/form-data 里除了 file，还要带 kind 字段。strip()去掉前后空格。
    # kind 决定这个文件后续会填到 render 请求的哪个位置。
    kind = (request.form.get("kind") or "").strip()
    if kind not in ALLOWED_KINDS:
        return error_response(f"Unsupported upload kind: {kind}", 400)

    # upload_folder 来自统一配置，所有上传文件都被限制在这个根目录下面。
    # 每次上传再创建一个独立子目录，避免不同用户/不同文件互相覆盖。
    config = current_app.extensions["app_config"]
    upload_dir = _make_upload_dir(config.upload_folder)

    try:
        component_files = [item for item in request.files.getlist("files") if item.filename]
        if component_files:
            # 前端一次多选 shapefile 组件时使用 files 字段。
            # 这比要求新手手动打 zip 更友好。
            saved_path, final_suffix = _save_shapefile_components(kind, component_files, upload_dir)
        else:
            # 浏览器上传单文件时，文件本体会放在 request.files["file"]。
            # 如果没有 file 或文件名为空，说明前端表单没有正确提交文件。
            file = request.files.get("file")
            if file is None or not file.filename:
                return error_response("Missing uploaded file.", 400)

            # 先用原始文件名判断后缀，只允许当前 kind 支持的格式。
            # 这样能尽早拦截明显不匹配的上传，避免 ArcPy 到后面才报复杂错误。
            suffix = Path(file.filename).suffix.lower()
            allowed_suffixes = ALLOWED_SUFFIXES_BY_KIND[kind]
            if suffix not in allowed_suffixes:
                return error_response(f"Unsupported file suffix for {kind}: {suffix}", 400)

            # zip 继续兼容；geojson、xlsx、aprx 这类单文件格式直接保存即可。
            if suffix == ".zip":
                saved_path, final_suffix = _save_shapefile_zip(file, upload_dir)
            else:
                saved_path = _save_regular_file(file, upload_dir)
                final_suffix = suffix
    except ValueError as exc:
        # 上传文件格式错误属于调用方问题，返回 400 给前端展示。
        return error_response(str(exc), 400)

    # 返回的 path 是后端本地绝对路径。
    # 前端下一步可以把这个 path 放进 /api/render 的 inputs 或 template_project 字段。
    return success_response(
        {
            # 当前没有数据库，所以 file_id 先用本次上传目录名。
            # 如果后续接数据库，可以把这里替换成数据库记录 ID。
            "file_id": upload_dir.name,
            "kind": kind,
            "original_name": saved_path.name,
            "path": str(saved_path.resolve()),
            "suffix": final_suffix,
            "size_bytes": saved_path.stat().st_size if saved_path.exists() else 0,
        }
    )


def _make_upload_dir(upload_root: Path) -> Path:
    """创建本次上传的独立目录。

    使用日期目录方便人肉排查；使用 uuid 避免同名文件互相覆盖。
    """
    # 目录结构示例：
    # uploads/20260420/9f2c.../
    # 日期方便定位问题，uuid 保证每次上传都有独立空间。
    upload_dir = upload_root / datetime.now().strftime("%Y%m%d") / uuid.uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _save_regular_file(file: FileStorage, upload_dir: Path) -> Path:
    """保存普通单文件上传，例如 geojson、xlsx、aprx。"""
    # secure_filename 会清理浏览器传来的文件名，去掉路径分隔符等不安全字符。
    # 例如用户上传 "../../a.geojson"，这里不会按原路径写到上级目录。
    filename = secure_filename(file.filename or "uploaded-file")
    if not filename:
        # 极端情况下，文件名清理后可能变成空字符串，给一个兜底名称。
        filename = "uploaded-file"
    target = upload_dir / filename
    file.save(target)
    return target


def _save_shapefile_zip(file: FileStorage, upload_dir: Path) -> tuple[Path, str]:
    """保存并解压 shapefile zip，返回主 `.shp` 文件路径。

    Shapefile 实际是一组同名文件，浏览器上传时必须打包成 zip。这里解压后查找
    第一个 `.shp` 文件，并把它的路径返回给 ArcPy。
    """
    # 先把 zip 原样保存下来，方便出错时排查原始上传文件。
    zip_path = _save_regular_file(file, upload_dir)
    extract_dir = upload_dir / "shapefile"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        # zipfile.ZipFile 只负责读取压缩包。
        # 真正解压时用 _safe_extract_zip，避免 zip 里藏 ../ 之类的危险路径。
        with zipfile.ZipFile(zip_path) as archive:
            _safe_extract_zip(archive, extract_dir)
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded zip file is invalid.") from exc

    # ArcPy 加载 shapefile 时需要主 .shp 文件路径。
    # zip 内可能带一层目录，所以用 rglob 递归查找。
    shp_files = sorted(extract_dir.rglob("*.shp"))
    if not shp_files:
        raise ValueError("No .shp file found in uploaded zip.")
    return shp_files[0], ".shp"


def _save_shapefile_components(kind: str, files: list[FileStorage], upload_dir: Path) -> tuple[Path, str]:
    """保存前端一次多选的 shapefile 组件，并返回主 `.shp` 路径。

    前端会把多个组件文件都放到 multipart/form-data 的 `files` 字段下。
    这里要求至少包含 `.shp/.shx/.dbf`，否则 ArcPy 即使拿到路径也无法正确读取。
    """
    if kind not in {"basin_boundary", "river_network"}:
        raise ValueError("Only basin_boundary and river_network support shapefile component uploads.")

    suffixes = {Path(item.filename or "").suffix.lower() for item in files}
    missing = REQUIRED_SHAPEFILE_COMPONENTS - suffixes
    if missing:
        raise ValueError("Please select at least .shp, .shx and .dbf files for a shapefile upload.")

    unsupported = suffixes - ALLOWED_SHAPEFILE_COMPONENTS
    if unsupported:
        unsupported_text = ", ".join(sorted(unsupported))
        raise ValueError(f"Unsupported shapefile component suffix: {unsupported_text}")

    component_dir = upload_dir / "shapefile"
    component_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    for file in files:
        saved_paths.append(_save_regular_file(file, component_dir))

    shp_files = sorted(path for path in saved_paths if path.suffix.lower() == ".shp")
    if not shp_files:
        raise ValueError("No .shp file found in uploaded shapefile components.")
    return shp_files[0], ".shp"


def _safe_extract_zip(archive: zipfile.ZipFile, extract_dir: Path) -> None:
    """安全解压 zip，阻止 `../` 这类路径穿越。"""
    # 先解析出最终解压根目录的绝对路径，后面每个成员都必须落在这个目录下。
    extract_root = extract_dir.resolve()
    for member in archive.infolist():
        # member.filename 是 zip 内部路径，不能直接信任。
        # resolve() 后再检查是否仍在 extract_root 下面，防止 ../../evil.py 写出上传目录。
        target = (extract_dir / member.filename).resolve()
        if not str(target).startswith(str(extract_root)):
            raise ValueError("Uploaded zip contains unsafe paths.")
        if member.is_dir():
            # zip 里可能显式包含目录项，遇到目录就创建后继续。
            target.mkdir(parents=True, exist_ok=True)
            continue
        # 普通文件先创建父目录，再把压缩包里的内容复制到目标文件。
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)
