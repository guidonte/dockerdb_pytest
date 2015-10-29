# -*- coding: utf-8 -*

import docker
import jinja2
import psycopg2

import pytest

import os
import shutil
import time
import json
import pprint
import md5


@pytest.yield_fixture(scope='class')
def dockerdb(request):
    """Connection to a dockerized Postgresql instance filled with data."""
    client = docker.Client(base_url='unix://var/run/docker.sock')

    curdir = os.path.dirname(os.path.abspath(request.module.__file__))
    tmpdir = pytest.ensuretemp('docker')
    tmpdir.chdir()

    DBTIMEOUT = getattr(request.cls, 'DBTIMEOUT', 60)
    DBNAME = getattr(request.cls, 'DBNAME', 'testdb')

    signature = ''

    files = getattr(request.cls, 'DATA', [])
    for f in files:
        src = os.path.join(curdir, 'data', f)
        shutil.copy(src, tmpdir.strpath)
        with open(src) as f:
            content = f.read()
        signature = md5.md5(content + signature).hexdigest()

    sql = getattr(request.cls, 'SQL', [])
    for s in sql:
        signature = md5.md5(s + signature).hexdigest()

    dockerfile = jinja2.Template('''
FROM ubuntu:15.04
MAINTAINER Guido Amoruso <guidonte@gmail.com>
RUN apt-get update && apt-get install -y postgresql-9.4
USER postgres
{% for file in FILES %}
COPY {{ file }} /tmp/
{% endfor %}
RUN echo {{ SIGNATURE }}
RUN /etc/init.d/postgresql start \
    && createdb {{ DBNAME }} \
    {% for file in FILES %} && psql -d {{ DBNAME }} < /tmp/{{ file }} {% endfor %} \
    {% if SQL %} && psql -d {{ DBNAME }} -c "{% for s in SQL %} {{ s }}; {% endfor %}" {% endif %}
RUN /etc/init.d/postgresql stop && echo done
RUN echo "host all all 0.0.0.0/0 trust" >> /etc/postgresql/9.4/main/pg_hba.conf
RUN echo "listen_addresses='*'" >> /etc/postgresql/9.4/main/postgresql.conf
EXPOSE 5432
VOLUME  ["/etc/postgresql", "/var/log/postgresql", "/var/lib/postgresql"]
CMD ["/usr/lib/postgresql/9.4/bin/postgres", "-D", "/var/lib/postgresql/9.4/main", "-c", "config_file=/etc/postgresql/9.4/main/postgresql.conf"]
    ''')

    dockerfile = dockerfile.render(FILES=files, SQL=sql, DBNAME=DBNAME,
                                   SIGNATURE=signature)
    dfile = tmpdir.join('Dockerfile')
    dfile.write(dockerfile)

    print "Rebuilding docker image..."
    img = client.build(path=tmpdir.strpath, rm=True, tag="test-xmlapi")
    pprint.pprint([json.loads(i) for i in img])

    container = client.create_container(
        image='test-xmlapi',
        name='test-xmlapi',
        ports=[5432],
        host_config=docker.utils.create_host_config(port_bindings={
            5432: None,
        }),
    )
    response = client.start(container=container.get('Id'))

    container = [c for c in client.containers()
                 if c['Id'] == container['Id']][0]

    public_port = container['Ports'][0]['PublicPort']

    t = time.time()
    while True:
        if time.time() - t > DBTIMEOUT:
            yield None
            break

        try:
            conn = psycopg2.connect(database=DBNAME, user='postgres',
                                    port=public_port, host='127.0.0.1')
        except psycopg2.OperationalError:
            print "Waiting for database startup..."
            time.sleep(2)
            continue
        except Exception, ex:
            print ex
            yield None
            break
        else:
            yield conn
            break

    response = client.remove_container(container=container.get('Id'),
                                       force=True)


@pytest.yield_fixture(scope='function')
def dockercursor(request, dockerdb):
    """Cursor for a dockerized Postgresql instance.

    It will create a fresh cursor for a clean database built with the
    'dockerdb' fixture. Data can be configured in the same way.
    """
    cursor = dockerdb.cursor()

    yield cursor

    cursor.close()
    dockerdb.rollback()
