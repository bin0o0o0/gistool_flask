import { describe, expect, it } from 'vitest'
import {
  collectBoundaryFiles,
  firstDemFile,
  isBoundaryFileName,
  isDemFileName
} from '@/utils/watershedUpload'

function file(name: string) {
  return new File(['fake'], name)
}

describe('watershedUpload helpers', () => {
  it('recognizes DEM raster suffixes', () => {
    expect(isDemFileName('dem.tif')).toBe(true)
    expect(isDemFileName('dem.TIFF')).toBe(true)
    expect(isDemFileName('dem.geojson')).toBe(false)
  })

  it('recognizes boundary file suffixes including shapefile components', () => {
    expect(isBoundaryFileName('basin.geojson')).toBe(true)
    expect(isBoundaryFileName('basin.kml')).toBe(true)
    expect(isBoundaryFileName('basin.shp')).toBe(true)
    expect(isBoundaryFileName('basin.shx')).toBe(true)
    expect(isBoundaryFileName('basin.txt')).toBe(false)
  })

  it('picks the first DEM file from a drop payload', () => {
    const result = firstDemFile([file('notes.txt'), file('first.tif'), file('second.tiff')])

    expect(result?.name).toBe('first.tif')
  })

  it('keeps only supported boundary files from a drop payload', () => {
    const result = collectBoundaryFiles([file('basin.shp'), file('basin.dbf'), file('readme.txt'), file('basin.prj')])

    expect(result.map((item) => item.name)).toEqual(['basin.shp', 'basin.dbf', 'basin.prj'])
  })
})
