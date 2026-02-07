# Importing voters

* Update the VOTER_FILE and DATABASE_OUT parameters in import_voters.py (DATABASE_OUT should be a temporary file that you inspect before moving it to database.json).
* Run the import_voters.py script.
  * Expects an Alabama Secretary of State-format voter file export.
  * Writes a single turf containing all voters (other future scripts will create other turfs).
* Restart the app service to pick up the new database.

Some todos:
* Title case voter and street names for display (not all caps)
* Display age, not birthdate (we only get age from SOS)
* Allow merging (not just overwriting) databases; this may be a separate script.

# Geocoding doors

Once you have imported voters you will probably want to geocode their doors so you can cut turf.

You can use the `geocode_voters.py` script for this. It references the [geocode](https://github.com/an-empty-string/geocode) repository. Getting data sources for geocoding and defining a correct `CompositeGeocoder` is unfortunately left as an exercise for the reader.

# Cutting turf

Use the `export_geocoded_voters.py` script to create `geocoded_doors.geojson`. Open this file as a vector layer in QGIS.

Create a SpatiaLite layer called "turfs" with two fields: `name` (string) and `car_id` (int), with Polygon geometry. Draw turfs as you like.

When you are done cutting turf, run `TURF_DATA_PATH=/path/to/your/layer_db.sqlite python3 update_voter_turfs.py` to match doors to turfs, and move the doors/voters into those turfs. You will need to restart the web app to see the results. Note that you don't have to cover _all_ voters with a turf; voters not in a turf will remain in the default "All Voters" turf.

The `update_voter_turfs` script also reorders doors in turfs. If you are in a grid city and are cutting griddy turfs, it will work basically perfectly. If you are not in a grid city, the lazy-TSP algorithm will try its best but probably fail quite miserably. Good luck! :3

# Getting Started

## Virtualenv
```sh
python -m venv .venv
source .venv/bin/activate
pip install .
python3 app.py
```

## uv
```sh
uv run app.py
```
