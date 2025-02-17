import os
# Add parent directory for imports
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0, parentdir)

import boto.swf
import log
import json
import random
import datetime
from optparse import OptionParser

"""
Amazon SWF S3Monitor starter
"""

class starter_S3Monitor():

    def start(self, settings, workflow="S3Monitor"):
        # Log
        identity = "starter_%s" % int(random.random() * 1000)
        logFile = "starter.log"
        logger = log.logger(logFile, settings.setLevel, identity)

        # Simple connect
        conn = boto.swf.layer1.Layer1(settings.aws_access_key_id, settings.aws_secret_access_key)
        if workflow:
            (workflow_id, workflow_name, workflow_version, child_policy,
             execution_start_to_close_timeout, input) = self.get_workflow_params(workflow, settings)

            logger.info('Starting workflow: %s' % workflow_id)
            try:
                response = conn.start_workflow_execution(settings.domain, workflow_id,
                                                         workflow_name, workflow_version,
                                                         settings.default_task_list, child_policy,
                                                         execution_start_to_close_timeout, input)

                logger.info('got response: \n%s' % json.dumps(response, sort_keys=True, indent=4))

            except boto.swf.exceptions.SWFWorkflowExecutionAlreadyStartedError:
                # There is already a running workflow with that ID, cannot start another
                message = ('SWFWorkflowExecutionAlreadyStartedError: There is already ' +
                           'a running workflow with ID %s' % workflow_id)
                print message
                logger.info(message)

    def get_workflow_params(self, workflow, settings):

        workflow_id = None
        workflow_name = None
        workflow_version = None
        child_policy = None
        execution_start_to_close_timeout = None

        input = None

        if workflow == "S3Monitor":
            # Standard article bucket monitor
            bucket = settings.bucket
            workflow_id = "S3Monitor"
        elif workflow == "S3Monitor_POA":
            # POA delivery bucket monitor
            bucket = settings.poa_bucket
            workflow_id = "S3Monitor_POA"

        if bucket is not None:
            # workflow_id as set above
            workflow_id = workflow_id
            workflow_name = "S3Monitor"
            workflow_version = "1.1"
            child_policy = None
            execution_start_to_close_timeout = str(60*25)
            input = '{"data": {"bucket": "' + bucket + '"}}'

        return (workflow_id, workflow_name, workflow_version, child_policy,
                execution_start_to_close_timeout, input)


if __name__ == "__main__":

    # Add options
    parser = OptionParser()
    parser.add_option("-e", "--env", default="dev", action="store", type="string",
                      dest="env", help="set the environment to run, either dev or live")
    parser.add_option("-w", "--workflow-name", default="S3Monitor", action="store",
                      type="string", dest="workflow", help="specify the workflow name to start")
    (options, args) = parser.parse_args()
    if options.env:
        ENV = options.env
    if options.workflow:
        workflow = options.workflow

    import settings as settingsLib
    settings = settingsLib.get_settings(ENV)

    o = starter_S3Monitor()

    o.start(settings=settings, workflow=workflow)
