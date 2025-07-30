#!/usr/bin/env python
import sys
import json
import psycopg2

"""
Sample schema dictionary :
------------------
{
   "tables" : [
        {
            "name" : "test1",
            "drop" : "false",
            "multicolumn_unique": [
                ["portal_name"]
            ],
            "columns" : [
                ["id", "serial", ["NOT NULL"]],
                ["portal_name", "character varying(100)", ["INDEX"]],
                ["customer_type", "character varying(50)", []],
                ["email", "character varying(100)", []],
                ["plan_name", "character varying(50)", []],
                ["old_plan_name", "character varying(50)", []],
                ["License_expiry", "date", []],
                ["device_limit", "integer", ["NOT NULL"]],
                ["lastlogin_time", "timestamp without time zone", []],
                ["disk_status", "character varying(50)" , ["NOT NULL"]],
                ["enrolleddevice_count", "integer", ["NOT NULL"]],
                ["report_date", "date", ["INDEX"]]
            ]
        },
        {
            "name" : "test2",
            "drop" : "true",
            "multicolumn_unique" : [],
            "columns" : [
                ["id", "integer", ["NOT NULL"]],
                ["portal_name", "character varying(100)", []],
                ["customer_type", "character varying(50)", []],
                ["email", "character varying(100)", []]
            ]
        }
    ]
}
----------------

#create a db connection <conn> and use it as the first param
#send the schema dictionary as the second param
#(optional) create a list of table to migrate from the schema. If not provided
            will migrate all tables in schema

Usage:
    mig_obj = Migrations(conn, schema_dict)
    mig_obj.migrate(["test1"])
"""

class Migrations:
    def __init__(self, conn, schema):
        self.conn = conn
        self.schema = schema

    def check_table_exists(self, table_name):
        """
        Check if a table exists in the connected PostgreSQL database.
        Args:
            conn (connection): A PostgreSQL connection object.
            schema (dict): Dictionary of table schemas to migrate
        Returns:
            True if the table exists,  otherwise.
        """
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT * FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = '{}';
            """.format(table_name))
            rows = cur.fetchall()
            cur.close()
                          
            return True if rows else False

        except Exception as e:
            print(e)

    def create_table(self, table):
        """
        Create a table in the connected PostgreSQL database.
        Args:
            table (dict): A dictionary containing table name and column information.
        """
        req_column_data = []
        try:
            req_column_data = []
            for columns in table.get('columns'):
                req_column_data.append('"'+columns[0]+'" '+columns[1]+' '+' '.join(constraint for constraint in columns[2] if constraint not in ["INDEX"]))
            
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE {}({});
            """.format(table.get("name"), ','.join(req_column_data)))
            self.conn.commit()
            cur.close()
            
            print("Created table {}".format(table.get("name")))

        except Exception as e:
            print(e)

    def drop_table(self, table_name):
        """
        Drop a table from the connected PostgreSQL database.
        Args:
            table_name (str): The name of the table to drop.
        """
        try:
            curr = self.conn.cursor() 
            curr.execute("""
                DROP table "{}";
            """.format(table_name))
            self.conn.commit()

            print("Dropped table {}".format(table_name))

        except Exception as e:
            print(e)

    def get_table_pk(self, table_name):
        """
        Retrieve the primary key of a given table in the connected PostgreSQL database.
        Args:
            table_name (str): The name of the table for which to retrieve the primary key.
        Returns:
            pk (str): The name of the primary key column if it exists, None otherwise.
        """
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT KU.table_name as TABLENAME, column_name as PRIMARYKEYCOLUMN FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS TC 
                INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS KU
                ON TC.CONSTRAINT_TYPE = 'PRIMARY KEY'
                AND TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME 
                AND KU.table_name = '{}'
                ORDER BY KU.TABLE_NAME,KU.ORDINAL_POSITION;
            """.format(table_name))
            pk_col = cur.fetchall()
            cur.close()

            pk = pk_col[0][1] if pk_col else None    
            return pk

        except Exception as e:
            print(e)
            sys.exit(1)

    def get_curr_tbschema(self, table_name):
        """
        Retrieve the current schema (column definitions) of a table in the connected PostgreSQL database.
        Args:
            table (dict): The name of the table to get the schema.
        """
        cur_column_data = []
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = '{}';
            """.format(table_name))
            cur_columns = cur.fetchall()
            cur = self.conn.cursor()
                
            cur = self.conn.cursor()
            cur.execute("""
                SELECT t1.COLUMN_NAME, STRING_AGG(COALESCE(t1.CONSTRAINT_TYPE,''),',')
                FROM
                    (SELECT c.TABLE_NAME, c.COLUMN_NAME, tc.CONSTRAINT_TYPE, ORDINAL_POSITION, t2.TABLE_NAME AS reference_table, t2.COLUMN_NAME AS reference_column
                    FROM INFORMATION_SCHEMA.COLUMNS c
                    LEFT JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu ON c.COLUMN_NAME = ccu.COLUMN_NAME AND c.TABLE_NAME = ccu.TABLE_NAME
                    LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc ON ccu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                    LEFT JOIN 
                        (SELECT  ccu1.TABLE_NAME, ccu1.COLUMN_NAME, rc.UNIQUE_CONSTRAINT_NAME, rc.CONSTRAINT_NAME FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc 
                        LEFT JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu1 ON ccu1.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME)t2
                    ON ccu.CONSTRAINT_NAME = t2.CONSTRAINT_NAME
                    GROUP BY c.TABLE_NAME, c.COLUMN_NAME, tc.CONSTRAINT_TYPE,ORDINAL_POSITION, t2.TABLE_NAME, t2.COLUMN_NAME)t1
                GROUP BY t1.TABLE_NAME, t1.COLUMN_NAME,t1.ORDINAL_POSITION 
                HAVING table_name = '{}'
                ORDER BY t1.TABLE_NAME, t1.ORDINAL_POSITION;
            """.format(table_name))
            col_constraints = cur.fetchall()
            cur = self.conn.cursor()
                
            cur = self.conn.cursor()
            cur.execute("""
                SELECT tablename,indexname FROM pg_indexes 
                WHERE tablename = '{}';
            """.format(table_name))
            index_columns = cur.fetchall()
            cur = self.conn.cursor()
            

            for column in cur_columns:
                constraints = []
                if column[2]:
                    data_type=column[1]+"("+str(column[2])+")"
                else:
                    data_type=column[1]
                
                if column[3] == "NO":
                    constraints.append('NOT NULL')

                for ind_col in index_columns:
                    const_name = table_name+"_"+column[0]+"_index"
                    
                    if ind_col[1]==const_name:
                        constraints.append('INDEX')
                
                for column2 in col_constraints:
                    if column[0]==column2[0]:
                        if column2[1] != '':
                            constraints.extend(column2[1].split(','))
                        
                        cur_column_data.append([column[0],data_type,constraints])

            return cur_column_data

        except Exception as e:
            print(e)
            sys.exit(1)

    def del_col(self, table_name, column):
        """
        Delete a column from the specified table in the database.
        Args:
            table_name (str): The name of the table from which to delete the column.
            column (str): The name of the column to delete.
        """
        status = 0
        try:
            cur = self.conn.cursor()
            cur.execute("""
                ALTER TABLE {} 
                DROP COLUMN "{}";
            """.format(table_name, column))
            self.conn.commit()
            cur.close()
            
            print("Deleted column {} for table {}".format(column,table_name))
            status = 1

        except Exception as e:
            print(e)
            print("Unable to delete column {} for table {}".format(column,table_name))

        return status

    def add_col(self, table_name, column):
        """
        Add a column to the specified table in the database.
        Args:
            table_name (str): The name of the table to which to add the column.
            column (str): A list containing column details [column_name, data_type, constraints].
        """
        status = 0
        try:
            cur = self.conn.cursor()

            cur.execute("""
                ALTER TABLE {}
                ADD COLUMN "{}" {};
            """.format(table_name, column[0], column[1], ' '.join(column[2])))
            self.conn.commit()
            cur.close()
            print("Created column {} for table {}".format(column,table_name))
            status = 1

        except Exception as e:
            print(e)
            print("Unable to create column {} for table {}".format(column,table_name))

        return status

    def attach_sequence_if_notexists(self, table_name, column):
        """
        Creates a serial sequence in db if not exists and attaches it to the column
        Args:
            table_name (str): The name of the table to which to add the column.
            column (str): A list containing column details [column_name, data_type, constraints].
        """
        status = 0
        try:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE SEQUENCE IF NOT EXISTS 
                "public.{}_{}_seq" 
                OWNED BY "public"."{}"."{}";
                ALTER SEQUENCE "public.{}_{}_seq" 
                OWNED BY "public"."{}"."{}";
            """.format(table_name, column[0], table_name, column[0],
                        table_name, column[0], table_name, column[0]))
            self.conn.commit()
            cur.close()
            print("Created and attached serial sequence to {} if not already".format(column[0]))
            status = 1
         
        except Exception as e:
            print(e)
            print("Unable to attach sequence to column {} for table {}".format(column,table_name))  
        
        return status

    def alter_column_datatype(self, table_name, column):
        """
        Alter the data type of a column in the specified table.
        Args:
            table_name (str): The name of the table whose column's data type will be altered.
            column (str): A list containing column details [column_name, new_data_type].
        Returns:
            status (int): An integer representing the status (1 for success, 0 for failure).
        """
        try:
            status = 0
            if column[1] == "serial":
                status += self.attach_sequence_if_notexists(table_name, column)

            else:
                cur = self.conn.cursor()
                cur.execute("""
                    ALTER TABLE {} 
                    ALTER COLUMN "{}" 
                    TYPE {}
                    USING "{}"::{};
                """.format(table_name, column[0], column[1], column[0], column[1]))
                self.conn.commit()
                cur.close()
                    
                print("datatype updated for column {} of table {}".format(column[0],table_name))
                status = 1
            
        except Exception as e:
            print(e)
            status = 0
        
        return status

    def compare_multicolumn_constraints(self, table):
        """
        Compare multicolumn constraints of the table
        Args:
            table (dict): A dictionary containing table name and column information.
        Returns:
            status (int): An integer representing the status (1 for success, 0 for failure).
        """
        status = 0
        table_name = table.get('name')
        cur = self.conn.cursor()
        cur.execute("""
                SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE 
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                WHERE TABLE_NAME = '{}';
            """.format(table_name))
        cur_multi_constraints = cur.fetchall()
        cur.close()
        tablename_frmted = table_name.replace("_", "")
        
        cur_multicol_unique = [
            const[0].replace("multi_","").replace(tablename_frmted, "").replace("_key","").split("_")[1:]
            for const in cur_multi_constraints 
            if const[1] == "UNIQUE" and const[0].startswith("multi")
        ]

        req_multicol_unique = table.get('multicolumn_unique')
        
        for req_const_list in req_multicol_unique :
            req_const_list_replaced = [col.replace("_","").lower() for col in req_const_list]
            for cur_const in cur_multicol_unique:
                if set(req_const_list_replaced) == set(cur_const):
                    break     
            else:
                #add req_const_list
                const_name = "multi_{}_{}_key".format(tablename_frmted, "_".join(req_const_list_replaced))
                col_str = '"' + '", "'.join(req_const_list) + '"'
                cur = self.conn.cursor()
                try:
                    cur.execute("""
                    ALTER TABLE {} 
                    ADD CONSTRAINT {} UNIQUE ({});
                    """.format(table_name, const_name, col_str))
                    self.conn.commit()
                    cur.close()
                    print("Constraint {} added to columns {} of table {}".format(const_name, col_str, table_name))
                    status = 1
                except Exception as e:
                    self.conn.rollback()
                    print(e)
                    print("Unable to add constraint {} to columns {} of table {}".format(const_name, col_str, table_name))
        
        #remove req_const_list
        for cur_const in cur_multicol_unique:
            for req_const_list in req_multicol_unique :
                req_const_list_replaced = [col.replace("_","").lower() for col in req_const_list]
                if set(req_const_list_replaced) == set(cur_const):
                    break 
            else:
                const_name = "multi_{}_{}_key".format(tablename_frmted, "_".join(cur_const))
                cur = self.conn.cursor()
                try:
                    cur.execute("""
                    ALTER TABLE {} 
                    DROP CONSTRAINT {};
                    """.format(table_name, const_name))
                    self.conn.commit()
                    cur.close()
                    print("Constraint {} dropped on table {}".format(const_name, table_name))
                    status = 1
                except Exception as e:
                    self.conn.rollback()
                    print(e)
                    print("Unable to remove constraint {} on table {}".format(const_name, table_name))          
        return status
                        
    def add_constraints(self, table_name, col_name, const):
        """
        Add constraints to a column in the specified table.
        Args:
            table_name (str): The name of the table where constraints will be added.
            col_name (str): The name of the column to which the constraint applies.
            const (str): The constraint type (e.g., PRIMARY KEY, INDEX, NOT NULL, UNIQUE).
        Returns:
            status (int): An integer representing the status (1 for success, 0 for failure).
        """
        status = 0
        pk = self.get_table_pk(table_name)
        query = None
        
        try:
            if const == "PRIMARY KEY":
                if pk:
                    cur = self.conn.cursor()
                    cur.execute("""
                        ALTER TABLE {} 
                        DROP CONSTRAINT {}_pkey;
                    """.format(table_name, table_name))
                    self.conn.commit()
                    cur.close()
                    
                    print("Current Primary key of table {} removed".format(table_name))

                query = "ALTER TABLE {} ADD PRIMARY KEY ({});".format(table_name, col_name)

            elif const == "INDEX":
                query = "CREATE INDEX {}_{}_index ON {} ({});".format(table_name, col_name, table_name, col_name)

            elif const == "NOT NULL":
                query = 'ALTER TABLE {} ALTER COLUMN "{}" SET NOT NULL;'.format(table_name, col_name)

            elif const == "UNIQUE":
                query = "ALTER TABLE {} ADD CONSTRAINT {}_{}_key UNIQUE ({});".format(table_name, table_name, col_name, col_name)

            else:
                print("Unknown constrain {}... please check the table schema".format(const))

            if query:
                cur = self.conn.cursor()
                cur.execute(query)
                self.conn.commit()
                cur.close()
                    
                print("Constraint {} added to column {} of table {}".format(const,col_name,table_name))
                status = 1

        except Exception as e:
            print(e)
            print("Unable to add constraint {} to column {} of table {}".format(const,col_name,table_name)) 
        
        return status   

    def drop_constraints(self, table_name, col_name, const):
        """
        Drop constraints from a column in the specified table.
        Args:
            table_name (str): The name of the table where constraints will be dropped.
            col_name (str): The name of the column from which the constraint will be dropped.
            const (str): The constraint type (e.g., PRIMARY KEY, INDEX, NOT NULL, UNIQUE).
        Returns:
            status (int): An integer representing the status (1 for success, 0 for failure).
        """
        status = 0
        pk = self.get_table_pk(table_name)
        query = None
        
        try:
            if const == "PRIMARY KEY":
                query = "ALTER TABLE {} DROP CONSTRAINT {}_pkey;".format(table_name ,table_name)

            elif const == "INDEX":
                query = "DROP INDEX {}_{}_index;".format(table_name, col_name)

            elif const == "NOT NULL":
                if col_name == pk:
                    return status
                else:
                    query = 'ALTER TABLE {} ALTER COLUMN "{}" DROP NOT NULL;'.format(table_name, col_name)

            elif const == "UNIQUE":
                query = "ALTER TABLE {} DROP CONSTRAINT {}_{}_key;".format(table_name, table_name, col_name)

            else:
                print("Unknown constrain {}... please check the table schema".format(const))

            if query:
                cur = self.conn.cursor()
                cur.execute(query)
                self.conn.commit()
                cur.close()
                
                print("Constraint {} dropped on column {} of table {}".format(const,col_name,table_name))
                status = 1
                
        except psycopg2.errors.UndefinedObject:
            if cur:
                cur.close()
            self.conn.rollback()       
            
        except Exception as e:
            print(e)
            print("Unable to delete constraint {} to column {} of table {}".format(const,col_name,table_name))

        return status

    def alter_column_constraints(self, table_name, old_col, new_col):
        """
        Alter constraints of a column by removing old constraints and adding new ones.
        Args:
            table_name (str): The name of the table where the column constraints will be altered.
            old_col (list): A list representing the old column definition [column_name, data_type, constraints].
            new_col (list): A list representing the new column definition [column_name, data_type, constraints].
        Returns:
            status (int): An integer representing the status (1 for success, 0 for failure).
        """
        rem_const = set(old_col[2])-set(new_col[2])
        add_const = set(new_col[2])-set(old_col[2])

        status = 0
        for const in rem_const:
            status += self.drop_constraints(table_name,old_col[0],const)

        for const in add_const:
            status += self.add_constraints(table_name,old_col[0],const)
            
        if status:
            print('All constraints updated for column {} of table {}'.format(old_col[0],table_name))
        
        return status

    def compare_schema(self, table, old_schema, new_schema):
        """
        Compare the current schema with a new schema, and perform necessary updates.
        Args:
            table (dict): A dictionary containing table name and column information.
            old_schema (list): A list of old column definitions [column_name, data_type, constraints].
            new_schema (list): A list of new column definitions [column_name, data_type, constraints].
        Returns:
            status (int): An integer representing the status of schema changes (1 if changes were made, 0 if not).
        """
        status = 0
        table_name = table.get("name")
        old_col = list(zip(*old_schema))[0]
        new_col = list(zip(*new_schema))[0]
        del_list = set(old_col)-set(new_col)
        add_list = set(new_col)-set(old_col)
        
        for column in del_list:
            status += self.del_col(table_name,column)

        for column in new_schema:
            for item in add_list:
                if item == column[0]:
                    status += self.add_col(table_name,column)
                    
        status += self.compare_multicolumn_constraints(table)

        for column in old_schema:
            for column2 in new_schema:
                if column[0] == column2[0]:
                    if column[1] != column2[1]:
                        status += self.alter_column_datatype(table_name,column2)
                        
                    if set(column[2]) != set(column2[2]):
                        status += self.alter_column_constraints(table_name, column, column2)

        return status

    def migrate(self, req_table_names = None):
        """
        Migrate table schemas defined in settings file to Database
        Compares defined schema to current table schema and modifies 
        the table accordingly

        Args:
            req_table_names (Optional | List): List of table names to migrate. 
                                               Migrates all tables if not provided
 
        Returns:
            status (int): Execution status of script. 1 -> failed, 0 -> success
        """
        status = 1
        if req_table_names:
            self.req_table_names = req_table_names
        else:
            self.req_table_names = [table.get('name') for table in self.schema.get('tables')]

        print("Running DB migrations script")  
        for table in self.schema.get("tables"):
            table_name = table.get("name")
            if table_name not in self.req_table_names:
                continue
            
            tb_exists = self.check_table_exists(table_name)
            if tb_exists:
                if table['drop'].lower() == "true":
                    self.drop_table(table_name)
                else:
                    print('Table {} already exists... comparing column attributes'.format(table_name))
                    curr_tbschema = self.get_curr_tbschema(table_name)
                    status = self.compare_schema(table, curr_tbschema, table.get("columns"))
                    if not status:
                        print("No changes detected for table {}".format(table_name))      
            else:
                if table['drop'].lower() == "true":
                    print("Skipping table creation for {}".format(table_name))
                else:
                    print('Table {} doesnt exist... Creating table'.format(table_name))
                    self.create_table(table)
                    for column in table.get("columns"):
                        if "INDEX" in column[2]:
                            self.add_constraints(table_name, column[0], "INDEX")
                    self.compare_multicolumn_constraints(table)
                        
            status = 0
            print("Migrated db changes successfully")

        return status
