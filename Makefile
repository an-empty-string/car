.PHONY: turfs.geojson
turfs.geojson:
	gdal vector convert --overwrite /home/tris/maps/hd25/turfs_data.sqlite turfs.geojson
