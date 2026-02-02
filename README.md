# Importing voters

* Update the VOTER_FILE and DATABASE_OUT parameters in import_voters.py (DATABASE_OUT should be a temporary file that you inspect before moving it to database.json).
* Run the import_voters.py script.
*     Expects an Alabama Secretary of State-format voter file export.
*     Writes a single turf containing all voters (other future scripts will create other turfs).
* Restart the app service to pick up the new database.

Some todos:
* Title case voter and street names for display (not all caps)
* Display age, not birthdate (we only get age from SOS)
* Allow merging (not just overwriting) databases; this may be a separate script.

# Geocoding doors

Once you have imported voters you will probably want to geocode their doors so you can cut turf.

You can use the `geocode_voters.py` script for this. It references the [geocode](https://github.com/an-empty-string/geocode) repository. Getting data sources for geocoding and defining a correct `CompositeGeocoder` is unfortunately left as an exercise for the reader.
