.PHONY: turfs.geojson reset-database
turfs.geojson:
	gdal vector convert --overwrite /home/tris/maps/hd25/turfs_data.sqlite turfs.geojson

reset-database:
	python3 -m car.script.import_voters
	python3 -m car.script.create_all_voters_phonebank_turf
	python3 -m car.script.geocode_doors
	python3 -m car.script.export_geocoded_voters
	RECREATE_TURFS=1 python3 -m car.script.update_voter_turfs
