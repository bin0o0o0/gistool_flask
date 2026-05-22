const DEM_SUFFIXES = new Set(['.tif', '.tiff'])
const BOUNDARY_SUFFIXES = new Set([
  '.geojson',
  '.json',
  '.kml',
  '.zip',
  '.shp',
  '.shx',
  '.dbf',
  '.prj',
  '.cpg',
  '.sbn',
  '.sbx',
  '.qix',
  '.xml'
])

function suffixOf(filename: string) {
  const dotIndex = filename.lastIndexOf('.')
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : ''
}

export function isDemFileName(filename: string) {
  return DEM_SUFFIXES.has(suffixOf(filename))
}

export function isBoundaryFileName(filename: string) {
  return BOUNDARY_SUFFIXES.has(suffixOf(filename))
}

export function firstDemFile(files: File[]) {
  return files.find((file) => isDemFileName(file.name))
}

export function collectBoundaryFiles(files: File[]) {
  return files.filter((file) => isBoundaryFileName(file.name))
}

export function isShapefileComponentSelection(files: File[]) {
  return files.some((file) => {
    const suffix = suffixOf(file.name)
    return suffix === '.shp' || suffix === '.shx' || suffix === '.dbf' || suffix === '.prj' || suffix === '.cpg' || suffix === '.sbn' || suffix === '.sbx' || suffix === '.qix' || suffix === '.xml'
  })
}
