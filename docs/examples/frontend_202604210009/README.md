# frontend_202604210009 示例数据

这套数据来自 README 快速使用章节中的 `frontend_202604210009` 测试例子，用来让读者直接复现一次“流域边界 + 河流 + 逐点站点样式”的出图流程。

## 输入数据

前端页面上传时使用这些文件：

| 页面字段 | 推荐上传文件 |
| --- | --- |
| `.aprx` 模板 | `inputs/template_project/gistool_test.aprx` |
| 流域边界 | `inputs/basin_boundary.zip` |
| 河流水系 | `inputs/river_network.zip` |
| 站点 Excel | `inputs/station_points/per_point_stations.xlsx` |

`inputs/basin_boundary/` 和 `inputs/river_network/` 里也保留了 Shapefile 的完整组件文件，方便需要单独检查 `.shp/.dbf/.prj` 的读者使用。前端测试时直接上传 zip 更省事。

## 站点 Excel 字段

`per_point_stations.xlsx` 的第一行是表头，第二行开始是点位数据：

| 字段 | 作用 |
| --- | --- |
| `name` | 点位名称 |
| `alias` | 可选显示名，用于区分同名点 |
| `lon` | 经度字段 |
| `lat` | 纬度字段 |
| `note` | 备注 |

页面里选择：

- 经度字段：`lon`
- 纬度字段：`lat`
- 名称字段：`name` 或 `alias`

## 参考结果

`expected-output/` 保存了这次测试运行后的参考输出，包括：

- `map.png`：最终出图结果。
- `result.json`：后端返回的结果摘要和 warning。
- `gistool_test.aprx`：后端复制并写入图层后的工程文件。
- `station_group_table_*.csv`、`station_layer_0_group_*.*`：后端为了逐点样式拆分生成的中间图层。

读者正常测试时只需要上传 `inputs/` 里的文件；`expected-output/` 用来对照自己的运行结果。
