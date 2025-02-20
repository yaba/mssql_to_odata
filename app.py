from flask import Flask, jsonify, request, make_response, render_template, redirect, url_for
import pyodbc
import datetime
from config import save_config, load_config
import urllib.parse
import logging

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

def get_db_connection(config=None, database=None):
    """Create a database connection using the given configuration."""
    if config is None:
        config = load_config()

    connection_params = {
        "DRIVER": f"{{{config['driver']}}}",
        "SERVER": config["server"],
        "UID": config["username"],
        "PWD": config["password"],
        "MARS_Connection": "Yes",
        "APP": "ODataSQL",
        "Trusted_Connection": "No",
        "encrypt": "no",
        "sslverify": "0",
    }
    if database:
        connection_params["DATABASE"] = database

    connection_string = ";".join(
        f"{k}={v}" for k, v in connection_params.items())
    return pyodbc.connect(connection_string)


def get_available_databases(config):
    """Get list of available databases"""
    conn = get_db_connection(config)
    cursor = conn.cursor()
    databases = [row.name for row in cursor.execute(
        "SELECT name FROM sys.databases WHERE database_id > 4")]
    conn.close()
    return databases


def get_database_objects(database):
    """Get all tables and views in the specified database"""
    config = load_config()
    conn = get_db_connection(config)
    cursor = conn.cursor()

    cursor.execute(f"USE {database}")

    query = """
    SELECT 
        TABLE_SCHEMA as schema_name,
        TABLE_NAME as name,
        TABLE_TYPE as type
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
    ORDER BY TABLE_TYPE, TABLE_SCHEMA, TABLE_NAME
    """
    cursor.execute(query)
    objects = [{"schema": row.schema_name, "name": row.name,
                "type": row.type} for row in cursor.fetchall()]
    conn.close()
    return objects


@app.route('/')
def index():
    """Main configuration page"""
    config = load_config()
    error_message = None
    connection_success = False

    if all([config.get('server'), config.get('username'), config.get('password')]):
        try:
            get_db_connection(config)
            connection_success = True
        except Exception as e:
            error_message = str(e)

    return render_template('index.html',
                           config=config,
                           connection_success=connection_success,
                           error_message=error_message)


@app.route('/save_config', methods=['POST'])
def save_configuration():
    """Save database configuration"""
    config = {
        'server': request.form['server'],
        'username': request.form['username'],
        'password': request.form['password'],
        'driver': request.form['driver']
    }
    save_config(config)
    return redirect(url_for('index'))


@app.route('/databases')
def list_databases():
    """Show available databases"""
    config = load_config()
    try:
        databases = get_available_databases(config)
        return render_template('databases.html',
                               databases=databases)
    except Exception as e:
        return render_template('databases.html',
                               error_message=str(e))


@app.route('/database/<database>')
def database_objects(database):
    """Show database objects and their OData URLs"""
    try:
        objects = get_database_objects(database)
        base_url = request.url_root.rstrip('/')
        return render_template('database.html',
                               database=database,
                               objects=objects,
                               base_url=base_url)
    except Exception as e:
        return render_template('database.html',
                               database=database,
                               error_message=str(e))


# OData Routes

def get_schema_info(conn, object_name):
    """Get schema information for tables and views"""
    cursor = conn.cursor()
    columns = cursor.columns(table=object_name).fetchall()
    schema = []

    pk_columns = []

    try:
        pk_query = """
        SELECT c.column_name
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE c
        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        ON c.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
        WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        AND c.TABLE_NAME = ?
        """
        cursor.execute(pk_query, (object_name,))
        pk_columns = [row.column_name for row in cursor.fetchall()]
    except:
        pass

    if not pk_columns:
        try:
            identity_query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            AND COLUMNPROPERTY(OBJECT_ID(TABLE_NAME), COLUMN_NAME, 'IsIdentity') = 1
            """
            cursor.execute(identity_query, (object_name,))
            pk_columns = [row.COLUMN_NAME for row in cursor.fetchall()]
        except:
            pass

    if not pk_columns:
        try:
            unique_idx_query = """
            SELECT COL_NAME(ic.object_id, ic.column_id) as column_name
            FROM sys.indexes i
            JOIN sys.index_columns ic 
            ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            WHERE i.is_unique = 1 
            AND OBJECT_NAME(i.object_id) = ?
            AND ic.key_ordinal = 1
            """
            cursor.execute(unique_idx_query, (object_name,))
            pk_columns = [row.column_name for row in cursor.fetchall()]
        except:
            pass

    if not pk_columns:
        try:
            non_nullable_query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            AND IS_NULLABLE = 'NO'
            """
            cursor.execute(non_nullable_query, (object_name,))
            pk_columns = [row.COLUMN_NAME for row in cursor.fetchall()]
        except:
            pass

    if not pk_columns and columns:
        pk_columns = [columns[0].column_name]

    for column in columns:
        col_name = column.column_name
        col_type = column.type_name

        edm_type = {
            'int': 'Edm.Int32',
            'bigint': 'Edm.Int64',
            'varchar': 'Edm.String',
            'nvarchar': 'Edm.String',
            'datetime': 'Edm.DateTimeOffset',
            'datetime2': 'Edm.DateTimeOffset',
            'date': 'Edm.Date',
            'decimal': 'Edm.Decimal',
            'money': 'Edm.Decimal',
            'float': 'Edm.Double',
            'bit': 'Edm.Boolean',
            'uniqueidentifier': 'Edm.Guid'
        }.get(col_type.lower(), 'Edm.String')

        schema.append({
            'name': col_name,
            'type': edm_type,
            'nullable': column.nullable,
            'is_key': col_name in pk_columns
        })

    if not any(col['is_key'] for col in schema):
        schema[0]['is_key'] = True

    return schema


@app.route('/odata/v4/<database>/', methods=['GET'])
def get_service_document(database):
    """Return the OData service document with available tables and views"""
    try:
        config = load_config()
        conn = get_db_connection(config, database)
        cursor = conn.cursor()

        query = """
        SELECT 
            TABLE_SCHEMA as schema_name,
            TABLE_NAME as name,
            TABLE_TYPE as type
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        """
        cursor.execute(query)
        objects = cursor.fetchall()

        service_doc = {
            "@odata.context": f"{request.url_root}odata/v4/{database}/$metadata",
            "value": [
                {
                    "name": obj.name,
                    "kind": "EntitySet",
                    "url": obj.name
                } for obj in objects
            ]
        }

        response = make_response(jsonify(service_doc))
        response.headers['OData-Version'] = '4.0'
        response.headers['Content-Type'] = 'application/json;odata.metadata=minimal'
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


@app.route('/odata/v4/<database>/<object_name>', methods=['GET'])
def get_object_data(database, object_name):
    """Return data from tables or views in OData v4 format"""
    try:
        config = load_config()
        conn = get_db_connection(config, database)
        cursor = conn.cursor()

        verify_query = """
        SELECT TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = ? AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        """
        cursor.execute(verify_query, (object_name,))
        if not cursor.fetchone():
            return jsonify({"error": "Object not found or not accessible"}), 404

        query = f"SELECT * FROM {object_name}"
        cursor.execute(query)

        columns = [column[0] for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            row_dict = {}
            for i, value in enumerate(row):
                if isinstance(value, datetime.datetime):
                    if value.tzinfo is None:
                        value = value.isoformat() + 'Z'
                    else:
                        value = value.isoformat()
                elif isinstance(value, datetime.date):
                    value = value.isoformat()
                elif isinstance(value, datetime.time):
                    value = value.isoformat()
                row_dict[columns[i]] = value
            rows.append(row_dict)

        response_data = {
            "@odata.context": f"{request.url_root}odata/v4/{database}/$metadata#{object_name}",
            "value": rows,
            "@odata.count": len(rows)
        }

        response = make_response(jsonify(response_data))
        response.headers['OData-Version'] = '4.0'
        response.headers['Content-Type'] = 'application/json;odata.metadata=minimal'
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


@app.route('/odata/v4/<database>/$metadata', methods=['GET'])
def get_metadata(database):
    """Return the EDM metadata document for both tables and views"""
    try:
        config = load_config()
        conn = get_db_connection(config, database)
        cursor = conn.cursor()

        query = """
        SELECT 
            TABLE_SCHEMA as schema_name,
            TABLE_NAME as name,
            TABLE_TYPE as type
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        """
        cursor.execute(query)
        objects = cursor.fetchall()

        metadata = ['<?xml version="1.0" encoding="utf-8"?>',
                    '<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">',
                    '    <edmx:DataServices>',
                    f'        <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="{database}">']

        for obj in objects:
            object_name = obj.name
            schema = get_schema_info(conn, object_name)

            metadata.append(f'            <EntityType Name="{object_name}">')

            key_properties = [col for col in schema if col['is_key']]
            if key_properties:
                metadata.append('                <Key>')
                for key_prop in key_properties:
                    metadata.append(
                        f'                    <PropertyRef Name="{key_prop["name"]}" />')
                metadata.append('                </Key>')

            for column in schema:
                nullable = 'true' if column['nullable'] else 'false'
                metadata.append(
                    f'                <Property Name="{column["name"]}" Type="{column["type"]}" Nullable="{nullable}" />')

            metadata.append('            </EntityType>')

        metadata.append(
            '            <EntityContainer Name="DefaultContainer">')
        for obj in objects:
            object_name = obj.name
            metadata.append(
                f'                <EntitySet Name="{object_name}" EntityType="{database}.{object_name}" />')
        metadata.append('            </EntityContainer>')

        metadata.extend(['        </Schema>',
                        '    </edmx:DataServices>',
                         '</edmx:Edmx>'])

        response = make_response('\n'.join(metadata))
        response.headers['OData-Version'] = '4.0'
        response.headers['Content-Type'] = 'application/xml'
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    print("\nSQL Server OData Service")
    print("------------------------")
    print("Server running at: http://localhost:5000")
    print("------------------------\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
