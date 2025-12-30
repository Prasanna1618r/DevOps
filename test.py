#!/bin/env python
import boto3
from botocore.exceptions import ClientError
import time
import datetime
import sys
import os
from os.path import expanduser
import argparse
from ConfigParser import SafeConfigParser
from django.conf import settings
import logging


FORMAT = "%(asctime)s {} {} - %(levelname)s - %(message)s".format(os.uname()[1],os.environ.get('technician','SYSTEM'))
DEFAULT_CREDENTIALS_FILE = expanduser('~/.mitsogo/credentials')

logger = logging.getLogger(__name__)
logging.basicConfig(format=FORMAT, level=os.environ.get('LOGLEVEL','INFO'))

configParser = SafeConfigParser()

def getconfig(profile,variable,environment,default=""):
    try:
        configParser.read(os.environ.get('SHARED_CREDENTIALS_FILE', DEFAULT_CREDENTIALS_FILE))
        value = configParser.get(profile, variable)
    except:
        value = os.environ.get(environment,default)
    return value
    

conf = { 
    'DATABASES' :{
        'default': {
            'ENGINE':'django.db.backends.postgresql_psycopg2',
            'NAME': getconfig('cloud','dbname','DBNAME'),
            'USER': getconfig('cloud','dbuser','DBUSER'),
            'PASSWORD': getconfig('cloud','dbpass','DBPASS'),
            'HOST': getconfig('cloud','dbhost','DBHOST'),
            'PORT': getconfig('cloud','dbport','DBPORT'),
            }   
        }
}

settings.configure(**conf)
from django.db import models


class AwsTable(models.Model):
    lightsaile_ip = models.CharField(max_length=100,blank=True,null=True)
    portal_name = models.CharField(max_length=100,null=True,blank=True)
    status = models.CharField(max_length=100,null=True,blank=True)
    instance_created_date = models.DateTimeField(null=True,blank=True)
    region = models.CharField(max_length=100,null=True,blank=True)
    aws_instance_name = models.CharField(max_length=100,null=True,blank=True)
    activated_date = models.DateTimeField(null=True,blank=True)
    tag = models.CharField(max_length=200,null=True,blank=True)
    exceptional_message = models.TextField(null=True,blank=True)
    deletion_status = models.CharField(max_length=500,null=True,blank=True)
    static_ip_name = models.CharField(max_length=500,null=True,blank=True)
    aws_db_location = models.CharField(max_length=500,null=True,blank=True)

    class Meta:
        app_label = 'instancemaker'

# snpshotname pattern = (aws_instance_name)_(date)_(backup)_([0-9]*)
# new instance_name pattern = (instance_name)_(resizedportal)_([0-9]*)
# static ip pattern = (instance_name)_static_ipi

if not os.environ.get('AWS_SHARED_CREDENTIALS_FILE',None):
    os.environ['AWS_SHARED_CREDENTIALS_FILE'] = '/var/local/etc/aws/credentials'

if not os.environ.get('AWS_PROFILE',None):
    os.environ['AWS_PROFILE'] = 'default'


def update_portalname_to_route53(portalname,ip,zone=None):
    os.environ['AWS_PROFILE'] = 'route53'
    HOSTEDZONE = 'Z3UDKA3M1BQ1FN'

    if not zone:
        zone = HOSTEDZONE

    add_the_dns = False
    record_data = {
                'ResourceRecords': [{'Value': ip}], 
                'Type': 'A',
                'Name': portalname,
                'TTL': 300
                }

    request_batch = {
                        'Action':'UPSERT',
                        'ResourceRecordSet':record_data
                    }

    changebatch = {
                    'Comment': 'inserting %s A record' %portalname,
                    'Changes' : [ request_batch ]
                    }
    try:
        s = boto3.Session()
        client = s.client('route53')

        response = client.change_resource_record_sets(HostedZoneId=zone,
                                                    ChangeBatch=changebatch
                                                )

        logger.debug(response)
        if response.get('ResponseMetadata').get('HTTPStatusCode',500) == 200:
            logger.info("successfully updated dns record for portal %s" %portalname)
            add_the_dns = True
        else:
            logger.error("error while updated dns record for portal %s" %portalname)
    except Exception as e:
        logger.error(e)
    logger.debug(add_the_dns)
    return add_the_dns


def checkLSresource(resourcetype,resource,conn_obj=None,region=None):
    output = {}
    status = False
    try:
        if not conn_obj:
            if region:
                conn_obj = boto3.client('lightsail',region_name = region)
            else:
                conn_obj = boto3.client('lightsail')

        if resourcetype == 'instance':
            resp = conn_obj.get_instance(instanceName = resource)
            output = resp.get('instance')

        elif resourcetype == 'snapshot':
            resp = conn_obj.get_instance_snapshot(instanceSnapshotName = resource)
            output = resp.get('instanceSnapshot')

        elif resourcetype == 'staticip':
            resp = conn_obj.get_static_ip(staticIpName = resource)
            output = resp.get('staticIp')

        logger.debug(output)
        status = True
        
    except ClientError as clienterror:
        if clienterror.response['Error']['Code'] == 'NotFoundException':
            status = False
        else:
            logger.warning(clienterror)

    return status,output

def restartLSinstance(instancename,conn_obj=None,region=None):
    try:
        if not conn_obj:
            if region:
                conn_obj = boto3.client('lightsail',region_name = region)
            else:
                conn_obj = boto3.client('lightsail')
        resp = conn_obj.reboot_instance(instanceName=instancename)['operations'][0]
        logger.debug(resp)
    except:
        resp = {'status':'failed'}
        logger.debug(resp)
    return resp

def stopLSinstance(instancename,conn_obj=None,region=None):
    try:
        if not conn_obj:
            if region:
                conn_obj = boto3.client('lightsail',region_name = region)
            else:
                conn_obj = boto3.client('lightsail')
        resp = conn_obj.stop_instance(instanceName=instancename)['operations'][0]
        logger.debug(resp)
    except:
        resp = {'status':'failed'}
        logger.debug(resp)
    return resp

def startLSinstance(instancename,conn_obj=None,region=None):
    try:
        if not conn_obj:
            if region:
                conn_obj = boto3.client('lightsail',region_name = region)
            else:
                conn_obj = boto3.client('lightsail')
        resp = conn_obj.start_instance(instanceName=instancename)['operations'][0]
        logger.debug(resp)
    except:
        resp = {'status':'failed'}
        logger.debug(resp)
    return resp

def sanitize(data):
    #return data.strip().upper()
    return data.strip()

class dummyinstance(object):
    def __init__(self,aws_instance_name,region):
        self.aws_instance_name = aws_instance_name
        self.region=region
    def save(self):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('action',type=str,help='stop,start,restart,reboot instance')
    parser.add_argument("--portalname",type=str,dest='portalname',help="mdm portal name ")
    parser.add_argument('--async',dest='async',action='store_true',help='whether wait for action to complete')
    

    args = parser.parse_args()

    instancename_list = []
    #instance_objs = []

    if args.portalname:
        try:
            portal_obj = AwsTable.objects.filter(portal_name__iexact=args.portalname.lower(),
                                                status='running'
                                                ).exclude(tag='purged').order_by('-id')
            if len(portal_obj) > 1:
                logger.error("more than 1 instance with given portalname exists")
                sys.exit(1)

            lsregion = portal_obj[0].region
            logger.debug(lsregion)
            instancename_list.append(portal_obj[0].aws_instance_name)
        except Exception as e:
            logger.error(e)
            sys.exit(1)
    else:
        logger.error("No instance Information is present")
        sys.exit(1)

    instancename_list = set(map(sanitize,instancename_list))

    for obj in instancename_list:
        instance_name = obj
        aws_region = lsregion
        logger.info("instance name = %s"%instance_name)
        logger.info("region = %s"%aws_region)

        boto_conn = boto3.client('lightsail',
                        region_name = aws_region
                       )



        isavailable,output = checkLSresource('instance',instance_name,boto_conn)

        if not isavailable:
            logger.error("lightsail instance with name %s does not exists"%instance_name)
            sys.exit(1)


        if output.get('isStaticIp',None) == False:
            logger.info("static ip not attached to instance %s"%instance_name)
        else:
            logger.info("static ip attached to instance %s"%instance_name)

        if args.action == 'stop':
            logger.info('stopping instance %s' %(instance_name))

            resp_stop = stopLSinstance(instance_name,boto_conn)
            
            if resp_stop.get('status',None) == 'failed':
                logger.error("error while stopping instance %s "%instance_name)
                logger.warning(resp_stop)

            if not args.async:
                isavailable,output = checkLSresource('instance',instance_name,boto_conn)

                while output.get('state',None)['name'] != 'stopped':
                    time.sleep(5)
                    isavailable,output = checkLSresource('instance',instance_name,boto_conn)
                logger.info("stopped instance %s"%instance_name)

        elif args.action == 'start':
            logger.info("starting instance %s"%instance_name)

            resp_start = startLSinstance(instance_name,boto_conn)
            logger.debug(resp_start)
            
            if resp_start.get('status',None) == 'failed':
                logger.error("error while starting instance %s "%instance_name)
                logger.warning(resp_start)

            if not args.async:
                isavailable,output = checkLSresource('instance',instance_name,boto_conn)

                while output.get('state',None)['name'] != 'running':
                    time.sleep(5)
                    isavailable,output = checkLSresource('instance',instance_name,boto_conn)
                logger.info("started instance %s"%instance_name)

        elif args.action == 'reboot':
            logger.info("rebooting instance %s"%(instance_name))

            resp = restartLSinstance(instance_name,boto_conn)
            logger.debug(resp)

            if resp.get('status',None) == 'failed':
                logger.error('error while restarting instance %s ' %(instance_name))
                logger.warning(resp)
            time.sleep(180)

            if not args.async:
                isavailable,output = checkLSresource('instance',instance_name,boto_conn)

                while output.get('state',None)['name'] != 'running':
                    time.sleep(5)
                    isavailable,output = checkLSresource('instance',instance_name,boto_conn)
                logger.info('started instance %s' %(instance_name))

                instance_publicip = output.get('publicIpAddress','unavailable')
                if instance_publicip == 'unavailable':
                    logger.error("public ip not yet allocated to instance %s" %instance_name)
                    sys.exit(1)
                
                if instance_publicip != portal_obj[0].lightsaile_ip:
                    logger.info("IP address of instance is %s" %instance_publicip)
                    logger.info("IP address in cloud database is %s" %portal_obj[0].lightsaile_ip)

                    portal_obj.update(lightsaile_ip=instance_publicip)
                    logger.info("cloud database updated with latest instance IP")

                    route_status = update_portalname_to_route53(args.portalname,instance_publicip,zone=None)

                    if not route_status:
                        logger.error("Error while updating route53")
                    else:
                        logger.info("updated route53 record with IP %s for portal %s" %(args.portalname,instance_publicip))
        elif args.action == 'restart':
            logger.info("restarting instance %s"%(instance_name))

            logger.info('stopping instance %s' %(instance_name))

            resp_stop = stopLSinstance(instance_name,boto_conn)
            
            if resp_stop.get('status',None) == 'failed':
                logger.error("error while stopping instance %s "%instance_name)
                logger.warning(resp_stop)

            isavailable,output = checkLSresource('instance',instance_name,boto_conn)

            while output.get('state',None)['name'] != 'stopped':
                time.sleep(5)
                isavailable,output = checkLSresource('instance',instance_name,boto_conn)
            logger.info("stopped instance %s"%instance_name)

            logger.info("starting instance %s"%instance_name)

            resp_start = startLSinstance(instance_name,boto_conn)
            logger.debug(resp_start)
            
            if resp_start.get('status',None) == 'failed':
                logger.error("error while starting instance %s "%instance_name)
                logger.warning(resp_start)

            isavailable,output = checkLSresource('instance',instance_name,boto_conn)

            while output.get('state',None)['name'] != 'running':
                time.sleep(5)
                isavailable,output = checkLSresource('instance',instance_name,boto_conn)
            logger.info("started instance %s"%instance_name)

            instance_publicip = output.get('publicIpAddress','unavailable')
            if instance_publicip == 'unavailable':
                logger.error("public ip not yet allocated to instance %s" %instance_name)
                sys.exit(1)
            
            if instance_publicip != portal_obj[0].lightsaile_ip:
                logger.info("IP address of instance is %s" %instance_publicip)
                logger.info("IP address in cloud database is %s" %portal_obj[0].lightsaile_ip)

                portal_obj.update(lightsaile_ip=instance_publicip)
                logger.info("cloud database updated with latest instance IP")

                route_status = update_portalname_to_route53(args.portalname,instance_publicip,zone=None)

                if not route_status:
                    logger.error("Error while updating route53")
                else:
                    logger.info("updated route53 record with IP %s for portal %s" %(args.portalname,instance_publicip))
                    
        else:
            logger.error('unknows action found')
            sys.exit(1)

