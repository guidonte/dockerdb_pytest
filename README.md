These fixures create dynamically a Dockerfile based on specified data,
build an image, spawn a container and wait for the database server to be
ready to accept requests; clean up the container on exit.

This approach has the following benefits:

    * does not use an existing local (or remote) Postgresql instance,
      making the test environment easier to setup and to clean up
    * populates the database only on the first time a specific test is
      run (when building the Docker image): on the following test runs, the
      database will just start fresh and prefilled with data
    * changes in the data are detected and applied based on the actual
      content, keeping the database in sync with the code

They require a local Docker installation with user permissions properly set.

Example usage:

class TestClass(object):
    # sql files to be found in the 'data' directory
    DATA = [
        'create_tables.sql',
        'required_data.sql',
    ]

    # list of SQL statements to load
    SQL = [
        ("INSERT into items (id, name) VALUES (1, 'foo')"),
        ("INSERT into items (id, name) VALUES (2, 'bar')"),
    ]

    def text_update(self, dockerdb):
        cursor = dockerdb.cursor()
        update_items(cursor, [])
