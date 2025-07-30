#!/usr/bin/env python
import sys
import os
import argparse
import pandas as pd
import psycopg2
from os.path import expanduser
from ConfigParser import SafeConfigParser

sys.path.append('../scriptfiles_common/')
from db_migrate import Migrations

configParser = SafeConfigParser()
DEFAULT_CREDENTIALS_FILE = os.path.join(expanduser("~"),'.mitsogo/credentials')

TABLE_SCHEMA = {
    "tables" : [
        {
            "name" : "portalreport_v2",
            "drop" : "false",
            "multicolumn_unique": [
                ["portal_name", "report_date"]
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
                ["disk_status", "integer" , ["NOT NULL"]],
                ["enrolleddevice_count", "integer", ["NOT NULL"]],
                ["disenrolleddevice_count", "integer", ["NOT NULL"]],
                ["disenrollpendingdevice_count", "integer", ["NOT NULL"]],
                ["android_device_count", "integer", ["NOT NULL"]],
                ["windows_device_count", "integer", ["NOT NULL"]],
                ["ios_device_count", "integer", ["NOT NULL"]],
                ["mac_device_count", "integer", ["NOT NULL"]],
                ["tvos_device_count", "integer", ["NOT NULL"]],
                ["linuxos_device_count", "integer", ["NOT NULL"]],
                ["visionos_device_count", "integer", ["NOT NULL"]],
                ["chromeos_device_count", "integer", ["NOT NULL"]],
                ["fireos_device_count", "integer", ["NOT NULL"]],
                ["androidtv_device_count", "integer", ["NOT NULL"]],
                ["enterprise_app_count", "integer", ["NOT NULL"]],
                ["kiosk_device_count", "integer", ["NOT NULL"]],
                ["live_kiosk_device_count", "integer", ["NOT NULL"]],
                ["use_location_api", "boolean", ["NOT NULL"]],
                ["vpp_check", "boolean", ["NOT NULL"]],
                ["ad_check", "boolean", ["NOT NULL"]],
                ["branch", "character varying(100)", []],
                ["revision_no", "character varying(100)", []],
                ["commit_no", "character varying(50)", []],
                ["technician_count", "integer", ["NOT NULL"]],
                ["dep_device_count", "integer", ["NOT NULL"]],
                ["preenrolled_devices", "integer", ["NOT NULL"]],
                ["apns_expiry", "date", []],
                ["wizard_completed", "boolean", ["NOT NULL"]],
                ["s3_upload_status", "character varying(50)", []],
                ["vpn_enabled", "boolean", ["NOT NULL"]],
                ["macos_vpn_enabled", "boolean", ["NOT NULL"]],
                ["android_enterprise_configured", "character varying(20)", []],
                ["portal_created_user_type", "character varying(50)", []],
                ["show_downgrade_modal", "boolean", ["NOT NULL"]],
                ["subscription_id", "character varying(50)", []],
                ["instance_in", "character varying(100)", []],
                ["region", "character varying(50)", []],
                ["ram_size" , "integer", ["NOT NULL"]],
                ["Active_device_count", "integer", ["NOT NULL"]],
                ["Active_device_percentage", "integer", ["NOT NULL"]],
                ["Last_reported", "timestamp without time zone", []],
                ["Gsuit_enabled", "boolean", ["NOT NULL"]],
                ["AzureAD_enabled", "boolean", ["NOT NULL"]],
                ["Filemanagement_enabled", "boolean", ["NOT NULL"]],
                ["subscription_status", "character varying(50)", ["NOT NULL"]],
                ["licensing_server", "character varying(100)", []],
                ["database_host", "character varying(100)", []],
                ["table_size", "integer", ["NOT NULL"]],
                ["ipaddress", "inet", []],
                ["windowsapp_status", "character varying(50)", []],
                ["command_queue", "integer", ["NOT NULL"]],
                ["command_success_rate", "integer", ["NOT NULL"]],
                ["report_date", "date", ["INDEX"]],
                ["created_date", "date", []],
                ["mdm_build", "character varying(250)", []],
                ["devops_django_version", "character varying(20)", ["NOT NULL"]],
                ["portal_django_version", "character varying(20)", ["NOT NULL"]],
                ["dbdatadir_status", "character varying(50)", []],
                ["mdm_group", "character varying(100)", []],
                ["reseller", "boolean", ["NOT NULL"]],
                ["3Dsecure", "boolean", ["NOT NULL"]],
                ["linuxappstatus", "character varying(50)", []],
                ["custom_mail_server", "boolean", ["NOT NULL"]],
                ["remarks", "character varying(250)", []]
            ]
        },
        {
            "name": "aggregated_report",
            "drop": "false",
            "multicolumn_unique": [],
            "columns": [
                ["report_date", "date", ["INDEX"]],
                ["total_device_limits", "numeric", ["NOT NULL"]],
                ["total_enrolleddevices", "numeric", ["NOT NULL"]],
                ["total_disenrolleddevices", "numeric", ["NOT NULL"]],
                ["total_disenrollpendingdevices", "numeric", ["NOT NULL"]],
                ["total_android_devices", "numeric", ["NOT NULL"]],
                ["total_windows_devices", "numeric", ["NOT NULL"]],
                ["total_ios_devices", "numeric", ["NOT NULL"]],
                ["total_mac_devices", "numeric", ["NOT NULL"]],
                ["total_tvos_devices", "numeric", ["NOT NULL"]],
                ["total_linuxos_devices", "numeric", ["NOT NULL"]],
                ["total_visionos_devices", "numeric", ["NOT NULL"]],
                ["total_chromeos_devices", "numeric", ["NOT NULL"]],
                ["total_fireos_devices", "numeric", ["NOT NULL"]],
                ["total_androidtv_devices", "numeric", ["NOT NULL"]],
                ["total_enterprise_apps", "numeric", ["NOT NULL"]],
                ["total_kiosk_devices", "numeric", ["NOT NULL"]],
                ["total_live_kiosk_devices", "numeric", ["NOT NULL"]],
                ["total_technicians", "numeric", ["NOT NULL"]],
                ["total_dep_devices", "numeric", ["NOT NULL"]],
                ["total_preenrolled_devices", "numeric", ["NOT NULL"]],
                ["total_active_devices", "numeric", ["NOT NULL"]],
            ]
        }
    ]
}

def getconfig(profile,variable,environment,default=""):
    try:
        configParser.read(os.environ.get('SHARED_CREDENTIALS_FILE', DEFAULT_CREDENTIALS_FILE))
        value = configParser.get(profile, variable)
    except:
        value = os.environ.get(environment,default)
    return value

def connect_db():
    DB_INFO = {
            'dbname': getconfig('portalanalytics','dbname','DBNAME'),
            'user': getconfig('portalanalytics','dbuser','DBUSER'),
            'password': getconfig('portalanalytics','dbpass','DBPASS'),
            'host': getconfig('portalanalytics','dbhost','DBHOST'),
            'port': getconfig('portalanalytics','dbport','DBPORT')
            }
    
    try:
        conn = psycopg2.connect(**DB_INFO)
        cur = conn.cursor()
        cur.execute("SHOW server_version;")
        record = cur.fetchone()
        cur.close()
        return conn

    except psycopg2.OperationalError as e:
        print("Failed to connect to the database: {}".format(e))
        sys.exit(2)

def sanitize_fields(fieldnames, incsvfile, outcsvfile, table_version='v1'):
    csv_data = pd.read_csv(incsvfile,error_bad_lines=False, warn_bad_lines=False)
    
    if table_version == 'v1':
        csv_data = csv_data.fillna("0")
    elif table_version == 'v2':
        for column in TABLE_SCHEMA['tables'][0].get("columns"):
            col_name, col_type, _ = column
            if col_name == 'report_date':
                csv_data[col_name] = pd.to_datetime(csv_data[col_name], format='%Y%m%d', errors='coerce').dt.strftime('%Y-%m-%d')
            if col_name == 'apns_expiry':
                csv_data[col_name] = csv_data['apns_expiry'].replace('no APNS', '1970-01-01')
            if col_name == 'lastlogin_time':
                csv_data[col_name] = csv_data['lastlogin_time'].replace('login unknown', '1970-01-01 00:00')
                csv_data[col_name] = csv_data['lastlogin_time'].replace('login disabled', '')

            if col_name in csv_data.columns:
                if col_type.startswith('character varying'):
                    csv_data[col_name] = csv_data[col_name].replace(
                            to_replace=[None, 'null', 'NULL', 'NaN', 'nan'],
                            value=""
                            ).astype(str)
                elif col_type == 'integer':
                    csv_data[col_name] = pd.to_numeric(csv_data[col_name], errors='coerce').fillna(0).astype('Int64')
                elif col_type == 'date':
                    csv_data[col_name] = pd.to_datetime(csv_data[col_name], errors='coerce')
                elif col_type == 'boolean':
                    csv_data[col_name] = csv_data[col_name].apply(
                        lambda x: True if str(x).strip().lower() in ['true', '1', 'yes'] else False
                    )
    
    csv_data = csv_data[fieldnames]
    csv_data.to_csv(outcsvfile, index=False)

def database_updation(conn, infile, outfile, column_list):
    status = 1
    sqlstr_v1 = 'COPY portalreport ("{}") FROM STDIN DELIMITER \',\' CSV HEADER;'.format('", "'.join(column_list))
    sqlstr_v2 = 'COPY portalreport_v2  ("{}") FROM STDIN DELIMITER \',\' CSV HEADER;'.format('", "'.join(column_list))
    
    try:
        sanitize_fields(column_list, infile, outfile, 'v1')
        with open(outfile) as f:
            cur = conn.cursor()
            cur.copy_expert(sqlstr_v1, f)
            print("Data is imported into portalanalytics database into portalreport table")
            cur.close()
        
        sanitize_fields(column_list, infile, outfile, 'v2')
        with open(outfile) as f:
            cur = conn.cursor()
            cur.copy_expert(sqlstr_v2, f)
            print("Data is imported into portalanalytics database into portalreport_v2 table")
            cur.close()
        status = 0
        
    except Exception as error:
        print("Error while updating reports to database: {}".format(error))
        
    finally:
        if conn:
            conn.commit()
        
    return status

def update_aggregated_report(conn, report_date):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO aggregated_report (report_date, total_device_limits, total_enrolleddevices, total_disenrolleddevices, total_disenrollpendingdevices, total_android_devices, total_windows_devices, total_ios_devices, total_mac_devices, total_tvos_devices, total_linuxos_devices, total_visionos_devices, total_chromeos_devices, total_fireos_devices, total_androidtv_devices, total_enterprise_apps, total_kiosk_devices, total_live_kiosk_devices, total_technicians, total_dep_devices, total_preenrolled_devices, total_active_devices)
            SELECT 
                report_date, 
                SUM(CAST(device_limit AS numeric)),
                SUM(CAST(enrolleddevice_count AS numeric)),
                SUM(CAST(disenrolleddevice_count AS numeric)), 
                SUM(CAST(disenrollpendingdevice_count AS numeric)), 
                SUM(CAST(android_device_count AS numeric)), 
                SUM(CAST(windows_device_count AS numeric)), 
                SUM(CAST(ios_device_count AS numeric)), 
                SUM(CAST(mac_device_count AS numeric)), 
                SUM(CAST(tvos_device_count AS numeric)), 
                SUM(CAST(linuxos_device_count AS numeric)), 
                SUM(CAST(visionos_device_count AS numeric)),
                SUM(CAST(chromeos_device_count AS numeric)), 
                SUM(CAST(fireos_device_count AS numeric)), 
                SUM(CAST(androidtv_device_count AS numeric)), 
                SUM(CAST(enterprise_app_count AS numeric)), 
                SUM(CAST(kiosk_device_count AS numeric)),  
                SUM(CAST(live_kiosk_device_count AS numeric)), 
                SUM(CAST(technician_count AS numeric)), 
                SUM(CAST(dep_device_count AS numeric)), 
                SUM(CAST(preenrolled_devices AS numeric)), 
                SUM(CAST("Active_device_count" AS numeric))                
            FROM portalreport_v2
            WHERE TO_CHAR(report_date, 'YYYYMMDD') = '{}'
            GROUP BY report_date;
        """.format(report_date))
        cur.close()
        print("Aggregated data updated successfully.")
    except Exception as e:
        print("Error updating aggregated report: {}".format(e))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("csvreport", type=str, help="csv report file location")
    parser.add_argument("-m", "--migrate", action="store_true", help="add flag to migrate schema to database")
    
    args = parser.parse_args()
    status = 1
    conn = connect_db()
    if args.migrate:
        mig_obj = Migrations(conn, TABLE_SCHEMA)
        status = mig_obj.migrate(["portalreport_v2", "aggregated_report"])
        sys.exit(status)
       
    if not os.path.exists(args.csvreport):
        print("csv file %s does not exist" %args.csvreport)
        sys.exit(status)

    report_date = args.csvreport.split('_',1)[1].split('.')[0]
    generated_csvreport = "csvreport_%s.csv" %report_date
    
    fieldnames = [field[0] for field in TABLE_SCHEMA['tables'][0].get("columns")]
    if 'id' in fieldnames: fieldnames.remove('id')
       
    status = database_updation(conn, args.csvreport, generated_csvreport, fieldnames)
    if status == 0:
        update_aggregated_report(conn, report_date)

    if os.path.exists(generated_csvreport):
        os.remove(generated_csvreport)
    
    if conn:
        conn.close()

    sys.exit(status)
