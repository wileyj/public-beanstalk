#!/usr/bin/python
""" Script to launch new beanstalk applications and environments """

import argparse
import os
import operator
import time
import json
import logging
import sys
from datetime import datetime
from difflib import SequenceMatcher
import pytz
import boto3
import jinja2

# python new-beanstalk.py --region us-east-1 --app app-name-dev-2 --env prod --minsize 1 --maxsize 1 --key_name base --instance t2.micro --elbtype external --disk singledisk --bucket bucket-name --app_type rails --env_vars '[
#     {
#         "RAILS_ENV": "production",
#         "RACK_ENV": "production",
#         "RAILS_ENV": "production",
#         "RDS_HOSTNAME": "<rds_hostname>",
#         "RDS_PASSWORD": "<rds password>",
#         "RDS_PORT": "<db port>",
#         "RDS_USERNAME": "<db user>",
#         "REGION": "us-east-1",
#         "S3_ASSET_BUCKET": "<s3 bucket assets>",
#         "SECRET_KEY_BASE": "<key>",
#         "SECRET_TOKEN": ",""<token>"
#     }
# ]'
# python new-beanstalk.py --region us-east-1 --app app-name-dev-2 --terminate Yes
# python new-beanstalk.py --region us-east-1 --app app-name-dev-2 --scale --maxsize 3 --minsize 2
# python new-beanstalk.py --region us-east-1 --app app-name-dev-2 --scale --maxsize 1 --minsize 1

env = {
    'prod' : "production",
    'staging' : "staging",
    'dev' : "dev",
    'qa' : "qa"
}
region_short = {
    'us-east-1' : 'use1',
    'us-west-2' : 'usw2',
    'us-west-1' : 'usw1'
}
virt_type = {
    't2.micro': 'hvm',
    't2.medium': 'hvm',
    't2.large': 'hvm',
    'm4.large': 'hvm',
    'm4.xlarge': 'hvm',
    'm4.2xlarge': 'hvm',
    'm4.4xlarge': 'hvm',
    'c4.large': 'hvm',
    'c4.xlarge': 'hvm',
    'c4.2xlarge': 'hvm',
    'm3.medium': 'pv',
    'm3.large': 'pv',
    'm3.xlarge': 'pv',
    'm3.2xlarge': 'pv',
    'c3.large': 'pv',
    'c3.xlarge': 'pv',
    'c3.2xlarge': 'pv'
}
app_stack = {
    'rails': 'running Ruby',
    'app': 'running Ruby',
    'tomcat': 'running Tomcat',
    'python': 'running Python'
}
ami_type = {
    'rails': 'rails',
    'app': 'base',
    'tomcat': 'tomcat',
    'python': 'python'
}
virt_name = {
    'hvm': 'hvm',
    'pv': 'paravirtual'
}
clear = lambda: os.system('clear')
epoch = int(time.time())
secs = 10
default_minsize = 1
default_maxsize = 1
cf_bucket = "s3-cloudformation"
default_lower = "5500000"
default_upper = "550000000000"
s3_list = {}
version_list = {}
ami_list = {}
stack_timeout = 3600

def get_archive(appname, environment, bucket, env_ver, app_archive):
    """ Retrieve application archive file """
    logging.warning("[ INFO   ] - Retrieving the Latest AMI")
    logging.warning("\n**************************************************")
    logging.warning("func - get_archive")
    logging.warning("\tappname: %s" % (appname))
    logging.warning("\tenvironment: %s" % (environment))
    logging.warning("\tbucket: %s" % (bucket))
    logging.warning("\tenv_ver: %s" % (env_ver))
    logging.warning("\tapp_archive: %s" % (app_archive))
    app_len = 0
    check_s3 = 0
    app_versions = beanstalk_client.describe_application_versions(
        ApplicationName=appname
    )['ApplicationVersions']
    describe_environments = beanstalk_client.describe_environments(
        ApplicationName=appname,
        EnvironmentNames=[appname+"-"+env_ver],
        IncludeDeleted=False
    )['Environments']
    describe_applications = beanstalk_client.describe_applications(
        ApplicationNames=[appname]
    )['Applications']
    logging.info("[ INFO   ] - Number of Matching Environments Found matching %s: %s" % (appname+"-"+env_ver, str(len(describe_environments))))
    logging.info("[ INFO   ] - Number of Matching Applications Found matching %s: %s" % (appname, str(len(describe_applications))))
    logging.warning("[ INFO   ] - Application Versions length: %s" % (str(len(app_versions))))
    logging.warning("\tapplications length: %s" % (len(describe_applications)))
    logging.warning("\tenvironments length: %s" % (len(describe_environments)))
    logging.warning("\tapp_versions: %s" % (app_versions))
    # logging.warning("\tdescribe_environments: %s" % (describe_environments))
    # logging.warning("\tdescribe_applications: %s" % (describe_applications))
    if len(describe_applications) > 0 and len(describe_environments) > 0:
        if describe_environments[0]['Status'] != "Terminated":
            logging.warning("[ ERROR ] - Application Environment %s Already Exists in %s" % (appname+"-"+env_ver, appname))
            logging.warning("Exiting...\n")
            exit(-3)
    if len(describe_applications) == 0:
        logging.warning("\n[ INFO  ] - Application %s Doesn't Exist yet" % (appname))
        logging.warning("[ INFO  ] - Creating Application Launch Template for %s" % (appname))
        init_application(appname)
    if len(app_versions) > 0:
        found_archive = 0
        logging.warning("\n[ INFO   ] - Looking in Beanstalk for the newest Archive: ")
        if len(app_archive.split(".")) > 1:
            app_archive = app_archive.split(".")[0]
        for release in app_versions:
            # logging.warning("found app: %s" % (release['SourceBundle']['S3Key']))
            if release['ApplicationName'] == appname:
                version_list[release['DateCreated']] = release['SourceBundle']['S3Key']
                if app_archive != "":
                    diff = SequenceMatcher(None, app_archive, release['SourceBundle']['S3Key']).ratio()
                    logging.info("DIFF: %s :: %s" % (diff, release['SourceBundle']['S3Key']))
                    if diff >= 0.96:
                        tz = pytz.timezone('US/Eastern')
                        now = tz.localize(datetime.utcnow(), is_dst=None).astimezone(pytz.utc)
                        version_list[now] = release['SourceBundle']['S3Key']
                        found_archive = 1
                        break
        # logging.warning("app_archive: %s" % (app_archive))
        # logging.warning("found_archive: %s" % (found_archive))
        if app_archive != "" and found_archive == 0:
            check_s3 = 1
            logging.warning("check_s3: %s" % (check_s3))
        sorted_beanstalk = sorted(version_list.items(), key=operator.itemgetter(0), reverse=True)
        logging.warning("len(sorted_beanstalk): %s" % (len(sorted_beanstalk)))
        if len(sorted_beanstalk) != 0:
            app_archive = sorted_beanstalk[0][1]
            app_len = len(app_archive)

    if app_len < 1 or check_s3 == 1:
        found_archive = 0
        logging.warning("[ INFO   ] - Looking in S3 for the newest Archive")
        logging.warning("\tS3 Bucket: %s" % (bucket))
        logging.warning("\tS3 Archive Prefix: %s" % (appname))
        logging.warning("\tApp name arg: %s" % (appname))
        logging.warning("\tApp environment arg: %s" % (env_ver))
        response = s3_client.list_objects(
            Bucket=bucket,
            Prefix=appname
        )['Contents']
        if response:
            if len(args.app_archive.split(".")) > 1:
                logging.warning("app_archive_one: %s" % (app_archive))
                app_archive = app_archive.split(".")[0]
                logging.warning("app_archive_two: %s" % (app_archive))
            else:
                logging.warning("app_archive_three: %s" % (app_archive))
            for item in response:
                s3_list[item['LastModified']] = item['Key']
                if app_archive != "":
                    diff = SequenceMatcher(None, app_archive, item['Key']).ratio()
                    if diff >= 0.96:
                        tz = pytz.timezone('US/Eastern')
                        now = tz.localize(datetime.utcnow(), is_dst=None).astimezone(pytz.utc)
                        s3_list[now] = item['Key']
                        found_archive = 1
                        break
            if app_archive != "" and found_archive != 1:
                logging.warning("[ ERROR ] - Archive %s not found", (app_archive))
                exit(5)
            sorted_s3 = sorted(s3_list.items(), key=operator.itemgetter(0), reverse=True)
            app_archive = s3_list[sorted_s3[0][0]]
            app_len = len(app_archive)
    logging.warning("\t Defined app_len: %s" % (app_len))
    logging.warning("\t Defined app_archive: %s" % (app_archive))
    logging.warning("\t Defined app_name: %s" % (appname))
    logging.warning("\t Defined S3 Bucket: %s" % (bucket))
    logging.warning("\t Defined S3 Archive Prefix: %s" % (appname))
    logging.warning("\t Defined App name arg: %s" % (appname))
    logging.warning("\t Defined App environment arg: %s" % (env_ver))
    if  app_len < 1:
        logging.warning("[ ERROR ] - No Archive found in Beanstalk or S3 for %s in %s" % (appname, args.region))
        exit(1)

    else:
        logging.warning("[ INFO  ] - Found app_archive %s" % (app_archive))
        return app_archive

def launch_application(template_values, template_body, a_name):
    """ launch_application """
    logging.info("[ EXEC  ] - Launching New Application Stack (%s)" % (template_values['app_name']))
    logging.warning("\n**************************************************")
    logging.warning("func - launch_application")
    logging.warning("\ttemplate_body: %s" % (template_body))
    logging.warning("\ta_name: %s" % (a_name))
    cloudformation_client.create_stack(
        StackName=a_name+"-env",
        TemplateBody=template_body,
        TimeoutInMinutes=30,
        Capabilities=['CAPABILITY_IAM'],
        OnFailure='DELETE'
    )
    elapsed = 0
    while stack_status(a_name+"-env", "CREATE_IN_PROGRESS") == "CREATE_IN_PROGRESS":
        if elapsed < stack_timeout:
            status = stack_status(a_name+"-env", "CREATE_IN_PROGRESS")
            elapsed = elapsed + secs
            sys.stdout = Unbuffered(sys.stdout)
            print "[ INFO   ] - Creating Stack %s: (%s) %ss elapsed \r" % (a_name+"-env", status, elapsed)
            sys.stdout.flush()
            time.sleep(secs)
        else:
            logging.info("\nOperation Timed out after %is: " % (elapsed))
            exit(-10)
    logging.info("\n[ INFO  ] Completed Application Creation( status: %s)" % (stack_status(a_name+"-env", "CREATE_COMPLETE")))
    return 0

def launch_environment(template_values, template_body, e_name, a_name):
    """ launch_environment """
    logging.info("[ EXEC  ] - Launching New Environment Stack (%s)" % (e_name))
    logging.warning("\n**************************************************")
    logging.warning("func - launch_environment")
    logging.warning("\ttemplate_body: %s" % (template_body))
    logging.warning("\te_name: %s" % (e_name))
    logging.warning("\ta_name: %s" % (a_name))

    sns_arn = "arn:aws:sns:"+template_values['region']+":"+template_values['account']+":"+template_values['app_arn']
    cloudformation_client.create_stack(
        StackName=e_name,
        TemplateBody=template_body,
        TimeoutInMinutes=30,
        NotificationARNs=[sns_arn],
        Capabilities=['CAPABILITY_IAM'],
        OnFailure='DELETE'
    )
    elapsed = 0
    # clear()
    while env_status(a_name, e_name) != "Ready" and stack_status(e_name, "CREATE_IN_PROGRESS"):
        if elapsed < stack_timeout:
            elapsed = elapsed + secs
            sys.stdout = Unbuffered(sys.stdout)
            print "[ INFO   ] - Creating Environment: %s (%s) %ss elapsed \r" % (e_name, env_status(a_name, e_name), elapsed)
            sys.stdout.flush()
            time.sleep(secs)
        else:
            logging.info("\nOperation Timed out after %is: " % (elapsed))
            exit(-10)

    logging.info("\n[ INFO  ] Completed Environment Creation( status: %s)" % (env_status(a_name, e_name)))
    logging.debug("\tstack_status(%s, 'CREATE_IN_PROGRESS'): %s" % (e_name, stack_status(e_name, "CREATE_IN_PROGRESS")))
    logging.debug("\tstack_status(%s, 'DELETE_IN_PROGRESS'): %s" % (e_name, stack_status(e_name, "DELETE_IN_PROGRESS")))
    logging.debug("\tstack_status(%s, 'DELETE_COMPLETE'): %s" % (e_name, stack_status(e_name, "DELETE_COMPLETE")))
    return 0

def get_stack(region):
    """ Retrieve beanstalk stack to use """
    logging.info("[ INFO  ] - Retrieving Beanstalk Stack to use")
    logging.warning("\n**************************************************")
    logging.warning("func - get_stack")
    logging.warning("\tregion: %s" % (region))
    stacks = beanstalk_client.list_available_solution_stacks()
    stack_list = {}
    list_len = 0
    if len(stacks['SolutionStacks']) > 0:
        for item in stacks['SolutionStacks']:
            diff = SequenceMatcher(None, app_stack[args.app_type], item).ratio()
            if 0.282352 < diff < 0.282353:
                stack_list[item] = item
                sorted_stack = sorted(stack_list.items(), key=operator.itemgetter(1), reverse=True)
        list_len = len(sorted_stack)
    logging.info("[ INFO  ] - Length of Solution Stack List: %s" % (list_len))
    if  list_len == 0:
        logging.info("\n[ ERROR ] - No Solution Stack found in  %s" % (region))
        exit(2)
    else:
        logging.info("[ INFO  ] - Using solution stack: %s" % (sorted_stack[0][0]))
        return sorted_stack[0][0]

def parse_env(json_data):
    """ docstring """
    logging.info("[ INFO  ] - Parsing Env Variables")
    logging.warning("\n**************************************************")
    logging.warning("func - parse_env")
    data = json.loads(json_data)
    count = 0
    returned_json = ""
    env_data = {}
    for k in data[0]:
        count = count + 1
        var_value = data[0][k]
        env_data[k] = var_value
    logging.info("Num of Environment Variables: %s" % (str(len(env_data))))
    logging.info("Parsed Environment Variables:")
    for name, value in env_data.items():
        logging.info("\t%s: %s" % (name, value))
        returned_json = returned_json+'\n\t\t}, {'
        returned_json = returned_json+'\n\t\t"Namespace":  "aws:elasticbeanstalk:application:environment",'
        returned_json = returned_json+'\n\t\t"OptionName": "'+name+'",'
        returned_json = returned_json+'\n\t\t"Value":      "'+value+'"'
    logging.info("*****************************\n")
    return returned_json

def scale_beanstalk(scale_max, scale_min, app_name, env_name):
    """ docstring """
    logging.info("[ INFO   ] - Scaling %s in %s ( MinSize[%s], MaxSize[%s] )" % (env_name, app_name, str(scale_min), str(scale_max)))
    logging.warning("\n**************************************************")
    logging.warning("func - scale_beanstalk")
    logging.warning("\tscale_max: %s" % (str(scale_max)))
    logging.warning("\tscale_min: %s" % (str(scale_min)))
    beanstalk_client.update_environment(
        ApplicationName=app_name,
        EnvironmentName=env_name,
        OptionSettings=[{
            "Namespace"  : "aws:autoscaling:asg",
            "OptionName" : "MinSize",
            "Value"      : str(scale_min)
        }, {
            "Namespace"  : "aws:autoscaling:asg",
            "OptionName" : "MaxSize",
            "Value"      : str(scale_max)
        }, {
            "Namespace"  : "aws:autoscaling:updatepolicy:rollingupdate",
            "OptionName" : "MinInstancesInService",
            "Value"      : str(scale_min)
        }]
    )
    elapsed = 0
    # clear()
    while env_status(app_name, env_name) != "Ready":
        if elapsed < stack_timeout:
            sys.stdout.write("[ INFO   ] - Updating Beanstalk: %s (%s) %ss elapsed \r" % (env_name, env_status(app_name, env_name), elapsed))
            sys.stdout.flush()
            time.sleep(secs)
            elapsed = elapsed + secs
        else:
            logging.info("\nOperation Timed out after %is: " % (elapsed))
            exit(-10)
    logging.info("\n[ INFO   ] - %s Finshed Scaling\n" % (env_name))
    exit(0)

def get_ami(disk):
    """ docstring """
    logging.info("[ INFO  ] - Retrieving AMI ID")
    logging.info("\tDisk Type: %s" % (disk))
    logging.info("\tVirtualization Type: %s" % (virt_type[args.instance]))
    logging.info("\tApp Type: %s" % (args.app_type))
    logging.info("\tAMI Type: %s" % (ami_type[args.app_type]))
    logging.warning("\n**************************************************")
    logging.warning("func - get_ami")
    logging.warning("\tdisk: %s" % (disk))
    try:
        ami_app = ami_type[args.app_type]
    except KeyError:
        logging.info("[ ERROR ] - AMI_TYPE %s key NOT FOUND" % (ami_type[args.app_type]))
        logging.info("[ INFO  ] Defaulting to a type of 'base'")
        ami_app = "base"

    logging.debug("Setting ami_app to %s" % (ami_app))
    ami = "local_amzn-"+disk+"-"+virt_type[args.instance]+"_packer-"+ami_app+"-beanstalk"
    logging.warning("[ INFO  ] - Looking for AMI named: %s" % (ami))
    try:
        images = ec2_client.describe_images(
            Owners=[args.account],
            Filters=[{
                'Name': 'root-device-type',
                'Values': ['ebs']
            }, {
                'Name': 'virtualization-type',
                'Values': [virt_name[virt_type[args.instance]]]
            }, {
                'Name': 'name',
                'Values': [ami]
            }]
        )
        for image in images['Images']:
            ami_list[image['CreationDate']] = image['ImageId']
        if len(ami_list) > 0:
            logging.info("[ INFO  ] - Found AMI with id: %s" %(sorted(ami_list.items(), key=operator.itemgetter(0), reverse=True)[0][1]))
            return sorted(ami_list.items(), key=operator.itemgetter(0), reverse=True)[0][1]
        else:
            logging.info("[ ERROR ] - No suitable ami was found")
            exit(1)
    except IOError:
        logging.info("[ ERROR ] - No suitable ami was found")
        exit(1)

def init_environment(app):
    """ docstring """
    logging.info("[ EXEC ] - Launching env %s" % (app))
    logging.warning("\n**************************************************")
    logging.warning("func - init_environment")
    logging.warning("\tapp: %s" % (app))
    env_name = app.split("-")[0]
    env_title = app.split("-")[1]
    env_env = app.split("-")[2]
    logging.info("\n Init ")
    logging.warning("\tEnv Name: %s" % (env_name))
    logging.warning("\tEnv Title: %s" % (env_title))
    logging.warning("\tEnv Environment: %s" % (env_env))
    elb_scheme = ""
    if args.elbtype == "internal":
        elb_scheme = elb_scheme+'\n\t\t}, {'
        elb_scheme = elb_scheme+'\n\t\t"Namespace":  "aws:ec2:vpc",'
        elb_scheme = elb_scheme+'\n\t\t"OptionName": "ELBScheme",'
        elb_scheme = elb_scheme+'\n\t\t"Value":      "internal"'
    values = {
        'notify_email'    : args.notify,
        'archive'         : archive,
        'version_label'   : archive.split(".")[0].split("-")[3],
        'solution_stack'  : args.stack,
        'region'          : args.region,
        'env_name'        : env_title,
        'minsize'         : args.minsize,
        'maxsize'         : args.maxsize,
        'lower'           : args.lower,
        'upper'           : args.upper,
        'ssl_cert'        : args.cert,
        'key_name'        : args.key_name,
        'env_short_upper' : args.env.upper(),
        'env_lower'       : args.app_lower,
        'environment'     : env_env,
        'env_version'     : args.app_version,
        'app_arn'         : args.app_arn,
        'instance'        : args.instance,
        'account'         : args.account,
        'service_role'    : args.service_role,
        'iam_role'        : args.iam_role,
        'domain'          : args.domain,
        'ami_image'       : get_ami(args.disk),
        'env_vars'        : env_vars,
        'bucket'          : args.bucket,
        'healthcheck'     : args.healthcheck,
        'elbtype'         : elb_scheme,
        'sns_topic'       : env_name.upper()+"-"+env_title.title()+"-"+env_env.title(),
        'sns_topic_lower' : env_name.lower()+"-"+env_title.lower()+"-"+env_env.lower(),
        'region_short'    : region_short[args.region],
        'app_group'       : args.group
    }
    logging.info("[ EXEC  ] - Creating Environment Template For %s" % (app))
    name = env_name.lower()+"-"+env_title.lower()+"-"+env_env.lower()
    launch_environment(values, write_template(values, "env.j2", name+"-"+args.app_version+"-env"), name+"-"+args.app_version, name)

def init_application(app):
    """ docstring """
    logging.info("[ EXEC ] - Launching New Application: %s" % (app))
    app_name = app.split("-")[0]
    app_title = app.split("-")[1]
    app_env = app.split("-")[2]
    logging.warning("\n**************************************************")
    logging.warning("func: init_application")
    logging.warning("\tapp (init_application): %s" % (app))
    logging.warning("\tapp_name (init_application): %s" % (app_name))
    logging.warning("\tapp_title (init_application): %s" % (app_title))
    logging.warning("\tapp_env (init_application): %s" % (app_env))
    values = {
        'region' : args.region,
        'environment' : app_env.lower(),
        'app_name' : app_title,
        'app_version' : args.app_version,
        'sns_topic'      : app_name.upper()+"-"+app_title.title()+"-"+app_env.title(),
        'sns_topic_lower' : app_name.lower()+"-"+app_title.lower()+"-"+app_env.lower(),
        'account' : args.account,
        'app_group' : app_name.lower(),
    }
    logging.info("[ EXEC  ] - Creating Application Template For %s" % (app))
    name = app_name.lower()+"-"+app_title.lower()+"-"+app_env.lower()
    launch_application(values, write_template(values, "app.j2", name+"-app"), name)
    return 0

def write_template(template_values, template, b_name):
    """ Create cloudformation file from template """
    template_path = "/opt/scripts/beanstalk/templates"
    logging.info("[ EXEC  ] - Writing CF Json %s using Template: %s" % (b_name, template))
    logging.warning("\n**************************************************")
    logging.warning("func: init_application")
    logging.warning("\ttemplate: %s" % (template))
    logging.warning("\tb_name: %s" % (b_name))
    logging.warning("\ttemplate_path: %s" % (template_path))
    logging.warning("\tTemplate Values: %s" % (template_values))
    app_env = jinja2.Environment(loader=jinja2.FileSystemLoader([template_path]))
    template = app_env.get_template(template)
    result = template.render(template_values)
    json_file = "/var/tmp/cf-"+b_name+"-"+str(epoch)+".json"
    logging.info("\tCreating file: %s" % (json_file))
    os.open(json_file, os.O_CREAT)
    fd = os.open(json_file, os.O_RDWR)
    os.write(fd, result)
    file_stat = os.fstat(fd)
    os.close(fd)
    logging.info("[ INFO   ] - Wrote Template %s with size: %s" % (json_file, str(file_stat.st_size)))
    return result

def stack_status(stack, message):
    """
        Available options:
            CREATE_FAILED
            UPDATE_ROLLBACK_FAILED
            UPDATE_ROLLBACK_IN_PROGRESS
            CREATE_IN_PROGRESS
            UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS
            ROLLBACK_IN_PROGRESS
            DELETE_COMPLETE
            UPDATE_COMPLETE
            UPDATE_IN_PROGRESS
            DELETE_FAILED
            DELETE_IN_PROGRESS
            ROLLBACK_COMPLETE
            ROLLBACK_FAILED
            UPDATE_COMPLETE_CLEANUP_IN_PROGRESS
            CREATE_COMPLETE
            UPDATE_ROLLBACK_COMPLETE
    """
    try:
        response = cloudformation_client.list_stacks(StackStatusFilter=[message])['StackSummaries']
        if len(response) > 0:
            for item in response:
                if item['StackName'] == stack:
                    response2 = cloudformation_client.describe_stacks(
                        StackName=item['StackName']
                    )['Stacks']
                    return response2[0]['StackStatus']
        return " Waiting for Data "
    except IOError:
        logging.info("[ INFO  ] - Error Retrieving status of stack: %s " % (stack))
        return " Error Retrieving Data "

def env_terminate(stack):
    """ env_terminate """
    logging.info("[ INFO  ] - Terminating Environment")
    logging.warning("\n**************************************************")
    logging.warning("func: env_terminate")
    logging.warning("\tstack: %s" % (stack))
    cloudformation_client.delete_stack(StackName=stack)
    elapsed = 0
    while stack_status(stack, "DELETE_IN_PROGRESS") == "DELETE_IN_PROGRESS":
        if elapsed < 1000:
            status = stack_status(stack, "DELETE_IN_PROGRESS")
            elapsed = elapsed + secs
            sys.stdout.write("[ INFO   ] - Terminating Environment Stack: %s (%s) %ss elapsed \r" % (stack, status, elapsed))
            sys.stdout.flush()
            time.sleep(secs)
        else:
            logging.info("\nOperation Timed out after %is: " % (elapsed))
            exit(-10)
    logging.info("\n[ INFO   ] - Terminated %s\n" % (stack))
    exit(0)

def app_status(beanstalk_env):
    """ app_status """
    beanstalk_status = beanstalk_client.describe_environment_health(
        EnvironmentName=beanstalk_env,
        AttributeNames=['Status']
    )
    if len(beanstalk_status) > 0:
        return beanstalk_status['Status']
    else:
        return 1

def env_status(beanstalk_app, beanstalk_env):
    """ env_status """
    response = beanstalk_client.describe_environments(
        ApplicationName=beanstalk_app
    )['Environments']
    returned = "null"
    if len(response) > 0:
        for i in response:
            if i['EnvironmentName'] == beanstalk_env:
                if i['Status'] != "Terminated" and i['Status'] != "Terminating":
                    returned = i['Status']
    return returned

class Unbuffered(object):
    """ Class to push stdout buffer to screen immediately """
    def __init__(self, stream):
        """ docstring for linter """
        self.stream = stream
    def write(self, data):
        """ docstring for linter """
        self.stream.write(data)
        self.stream.flush()
    def __getattr__(self, attr):
        """ docstring for linter """
        return getattr(self.stream, attr)

class VAction(argparse.Action):
    """ docstring """
    def __call__(self, argparser, cmdargs, values, option_string=None):
        if values is None:
            values = '1'
        try:
            values = int(values)
        except ValueError:
            values = values.count('v') + 1
        setattr(cmdargs, self.dest, values)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--region",
        metavar="",
        default="",
        help="AWS Region"
    )
    parser.add_argument(
        "--app_archive",
        metavar="",
        default="",
        help="Application Archive File"
    )
    parser.add_argument(
        "--stack",
        metavar="",
        default="",
    )
    parser.add_argument(
        "--app",
        metavar="",
        default="",
        help="Beanstalk Environment Name ( App-Prod-1 )"
    )
    parser.add_argument(
        "--env",
        metavar="",
        default="",
        help="Environment ( dev, staging, prod )"
    )
    parser.add_argument(
        "--minsize",
        metavar="",
        default=default_minsize,
        help="Beanstalk Minimum Number of EC2 Instances"
    )
    parser.add_argument(
        "--maxsize",
        metavar="",
        default=default_maxsize,
        help="Beanstalk Minimum Number of EC2 Instances"
    )
    parser.add_argument(
        "--lower",
        metavar="",
        default="5500000",
        help="AutoScaling scale down metric"
    )
    parser.add_argument(
        "--upper",
        metavar="",
        default="5500000000000",
        help="AutoScaling scale up metric"
    )
    parser.add_argument(
        "--cert",
        metavar="",
        default="prod.local.com",
        help="SSL Certificate Name"
    )
    parser.add_argument(
        "--key_name",
        metavar="",
        default="base",
        help="AWS EC2 Keyname"
    )
    parser.add_argument(
        "--instance",
        metavar="",
        default="m3.medium",
        help="EC2 Instance Type"
    )
    parser.add_argument(
        "--service_role",
        metavar="",
        default="aws-elasticbeanstalk-service-role",
        help="Beanstalk EC2 Service Role"
    )
    parser.add_argument(
        "--scale",
        metavar="",
        nargs="?",
        default="",
        help="Scale the Beanstalk Env by n hosts"
    )
    parser.add_argument(
        "--terminate",
        metavar="",
        default="",
        help="Terminate the specified beanstalk env. Requires a 'Yes' arg"
    )
    parser.add_argument(
        "--env_vars",
        metavar="",
        default="",
        help="Env. Variables - add in valid json format"
    )
    parser.add_argument(
        "--notify",
        metavar="",
        default="user@email.com",
        help="Email account to notify of changes to stack"
    )
    parser.add_argument(
        "--iam_role",
        metavar="",
        default="Base",
        help="IAM Role to use"
    )
    parser.add_argument(
        "--domain",
        metavar="",
        default="domain.com",
        help="Domain used for launch"
    )
    parser.add_argument(
        "--bucket",
        metavar="",
        default="",
        help="Bucket used for the application archive"
    )
    parser.add_argument(
        "--healthcheck",
        metavar="",
        default="/status",
        help="HealthCheck URL for the ELB (default: HTTP /status)"
    )
    parser.add_argument(
        "--elbtype",
        metavar="",
        default="external",
        help="Type of ELB ( internal | external )"
    )
    parser.add_argument(
        "--disk",
        metavar="",
        default="singledisk",
        help="Disk Type of AMI (singledisk, multidisk)"
    )
    parser.add_argument(
        "--account",
        metavar="",
        default="",
        help="AWS Account ID"
    )
    parser.add_argument(
        "--app_type",
        metavar="",
        default="app",
        help="Application Type (rails, tomcat, ... )"
    )
    parser.add_argument(
        "-v",
        metavar="",
        nargs="?",
        action=VAction,
        dest="verbose"
    )
    args = parser.parse_args()
    # if args.verbose:
    if args.verbose == 4:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose == 3:
        logging.basicConfig(level=logging.ERROR)
    elif args.verbose == 2:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.warning("\tArguments Received:")
    logging.warning("\targs.region: %s" % (args.region))
    logging.warning("\targs.stack: %s" % (args.stack))
    logging.warning("\targs.app: %s" % (args.app))
    logging.warning("\targs.env: %s" % (args.env))
    logging.warning("\targs.minsize: %s" % (args.minsize))
    logging.warning("\targs.maxsize: %s" % (args.maxsize))
    logging.warning("\targs.lower: %s" % (args.lower))
    logging.warning("\targs.upper: %s" % (args.upper))
    logging.warning("\targs.cert: %s" % (args.cert))
    logging.warning("\targs.key_name: %s" % (args.key_name))
    logging.warning("\targs.instance: %s" % (args.instance))
    logging.warning("\targs.service_role: %s" % (args.service_role))
    logging.warning("\targs.scale: %s" % (args.scale))
    logging.warning("\targs.terminate: %s" % (args.terminate))
    logging.warning("\targs.notify: %s" % (args.notify))
    logging.warning("\targs.iam_role: %s" % (args.iam_role))
    logging.warning("\targs.domain: %s" % (args.domain))
    logging.warning("\targs.bucket: %s" % (args.bucket))
    logging.warning("\targs.healthcheck: %s" % (args.healthcheck))
    logging.warning("\targs.elbtype: %s" % (args.elbtype))
    logging.warning("\targs.disk: %s" % (args.disk))
    logging.warning("\targs.account: %s" % (args.account))
    logging.warning("\targs.app_type: %s" % (args.app_type))
    logging.warning("\targs.verbose: %s" % (args.verbose))
    logging.warning("\targs.env_vars%s" % (args.env_vars))

    if not args.region or not args.app:
        logging.info("[ ERROR ] - region and app args are required\n")
        parser.print_help()
        exit(1)

    token = args.app.split("-")
    if len(token) > 3:
        args.app_lower = args.app.lower()
        args.app_bu = args.app_lower.split("-")[0]
        args.app_name = args.app_lower.split("-")[1]
        args.app_env = args.app_lower.split("-")[2]
        args.app_version = args.app_lower.split("-")[3]
        if not args.app_version.isdigit():
            logging.info("[ ERROR ] - %s needs to be an integer" % (args.app_version))
            exit(4)

        args.app_arn = args.app.split("-")[0].upper() + "-" + args.app.split("-")[1].title()+"-"+args.app.split("-")[2].title()
        args.group = args.app.split("-")[0]
        args.beanstalk = args.app_bu+"-"+args.app_name + "-" + env[args.app_env]
        sns_topic = args.app_name+"-"+args.app_env
        sns_topic_lower = sns_topic.lower()

        logging.warning("\targs.app_lower: %s" % (args.app_lower))
        logging.warning("\targs.app_bu: %s" % (args.app_bu))
        logging.warning("\targs.app_name: %s" % (args.app_name))
        logging.warning("\targs.app_env: %s" % (args.app_env))
        logging.warning("\targs.app_version: %s" % (args.app_version))
        logging.warning("\targs.app_arn: %s" % (args.app_arn))
        logging.warning("\targs.group: %s" % (args.group))
        logging.warning("\targs.beanstalk: %s" % (args.beanstalk))
        logging.warning("\tsns_topic: %s" % (sns_topic))
        logging.warning("\tsns_topic_lower: %s" % (sns_topic_lower))

        beanstalk_client = boto3.client('elasticbeanstalk', region_name=args.region)
        ec2_client = boto3.client('ec2', region_name=args.region)
        s3_client = boto3.client('s3', region_name=args.region)
        cloudformation_client = boto3.client('cloudformation', region_name=args.region)
        if not args.app_lower.split("-")[2] in env:
            logging.info("\n[ ERROR ] - Environment %s not found" % (args.app_env))
            exit(2)

        if not args.app_lower.split("-")[3].isdigit():
            logging.info("\n[ ERROR ] - Bad Format for App %s " % (args.app))
            logging.info("\tex: app-name-dev-1")
            parser.print_help()
            exit(3)

        if args.terminate:
            if args.terminate == "Yes":
                logging.info("\n[ INFO   ] - Looking for stack %s in %s" % (args.app_lower, args.region))
                if env_status(args.beanstalk, args.app_lower) != "null":
                    logging.info("[ INFO   ] - Found exisiting stack %s. continuing..." % (args.app_lower))
                    env_terminate(args.app_lower)
                    exit(32)
                else:
                    logging.info("\n[ ERROR ] - Stack %s doesn't exist" % (args.app_lower))
                    exit(10)
            else:
                logging.info("\n[ ERROR ] - In order to terminate a named stack, you need to supply a 'Yes' argument (case-sensitive)")
                exit(10)
        else:
            if  int(args.minsize) > int(args.maxsize):
                logging.info("\tError: minsize (%s) must be <= maxsize(%s)" % (str(args.minsize), str(args.maxsize)))
                exit(5)

            if int(args.maxsize) == int(args.minsize):
                logging.info("[ INFO  ] - (detected maxize == minsize): maxsize required to be greater than minsize. Adding 1 to %s" % (args.maxsize))
                args.maxsize = int(args.maxsize)+1

            if int(args.maxsize) == 1:
                logging.info("[ INFO  ] - (detected maxsize == 1): maxsize required to be greater than 1. Adding 1 to %s" % (args.maxsize))
                args.maxsize = int(args.maxsize)+1

        if not args.stack:
            logging.info("[ INFO   ] - Retrieving the latest stack solution name %s" % (args.app_name))
            args.stack = get_stack(app_stack[args.app_type])
            logging.info("\tFound Solution Stack: %s" % (args.stack))

        if args.env_vars:
            logging.info("[ INFO   ] - Reading in json for env. vars")
            env_vars = parse_env(args.env_vars)
        else:
            env_vars = ""

        if args.maxsize != default_maxsize:
            args.maxsize = args.maxsize
        else:
            args.maxsize = default_maxsize
        if args.minsize != default_minsize:
            args.minsize = args.minsize
        else:
            args.minsize = default_minsize

        if args.scale != "":
            logging.info("\n[ INFO   ] - Scaling Beanstalk %s in %s" % (args.app_lower, args.region))
            if env_status(args.beanstalk, args.app_lower) != "null":
                scale_beanstalk(int(args.maxsize), int(args.minsize), args.beanstalk, args.app_lower)
            else:
                logging.info("[ ERROR ] - Beanstalk App %s in %s Not Found" % (args.app_lower, args.region))
                exit(5)
        archive = get_archive(args.beanstalk, env[args.app_env], args.bucket, args.app_lower.split("-")[3], args.app_archive)

        init_environment(args.app)
        exit(0)
    else:
        logging.info("\n[ ERROR ] - App Name is wrong format: %s" % (args.app))
        logging.info("\tex: <company>-<appname>-<environment>-<stage>")
        parser.print_help()
        exit(4)
