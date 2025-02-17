import boto.swf
import settings as settingsLib
import log
import json
import random
import importlib
import os
import time
from optparse import OptionParser
from provider import process

import workflow
import newrelic.agent

"""
Amazon SWF decider
"""

def decide(ENV, flag):
    # Specify run environment settings
    settings = settingsLib.get_settings(ENV)

    # Decider event history length requested
    maximum_page_size = 100

    # Log
    identity = "decider_%s" % os.getpid()
    logFile = "decider.log"
    #logFile = None
    logger = log.logger(logFile, settings.setLevel, identity)

    # Simple connect
    conn = boto.swf.layer1.Layer1(settings.aws_access_key_id, settings.aws_secret_access_key)

    token = None
    application = newrelic.agent.application()

    # Poll for a decision task
    while flag.green():
        if token is None:
            logger.info('polling for decision...')

            decision = conn.poll_for_decision_task(settings.domain,
                                                   settings.default_task_list,
                                                   identity, maximum_page_size)

            # Check for a nextPageToken and keep polling until all events are pulled
            decision = get_all_paged_events(decision, conn, settings.domain,
                                            settings.default_task_list,
                                            identity, maximum_page_size)

            token = get_taskToken(decision)
            logger.info('got token: %s', token)

            if isinstance(decision, dict) and "startedEventId" in decision and decision["startedEventId"] == 0:
                logger.debug('got decision: \n%s' % json.dumps(decision, sort_keys=True, indent=4))
            else:
                logger.info('got decision: \n%s' % json.dumps(decision, sort_keys=True, indent=4))

            if token is not None:
                # Get the workflowType and attempt to do the work
                workflowType = get_workflowType(decision)
                with newrelic.agent.BackgroundTask(application, name=workflowType, group='decider.py'):
                    if workflowType is not None:

                        logger.info('workflowType: %s' % workflowType)

                        # Instantiate and object for the workflow using eval
                        # Build a string for the object name
                        workflow_name = get_workflow_name(workflowType)

                        # Attempt to import the module for the workflow
                        if import_workflow_class(workflow_name):
                            # Instantiate the workflow object
                            workflow_object = get_workflow_object(workflow_name, settings,
                                                                  logger, conn, token, decision,
                                                                  maximum_page_size)

                            # Process the workflow
                            try:
                                success = workflow_object.do_workflow()
                            except Exception as e:
                                success = None
                                logger.error('error processing workflow %s' %
                                             workflow_name, exc_info=True)

                            # Print the result to the log
                            if success:
                                logger.info('%s success %s' % (workflow_name, success))

                        else:
                            logger.info('error: could not load object %s\n' % workflow_name)

        # Reset and loop
        token = None

    logger.info("graceful shutdown")

def get_all_paged_events(decision, conn, domain, task_list, identity, maximum_page_size):
    """
    Given a poll_for_decision_task response, check if there is a nextPageToken
    and if so, recursively poll for all workflow events, and assemble a final
    decision response to return
    """

    # First check if there is no nextPageToken, if there is none
    #  return the decision, nothing to page
    next_page_token = None
    try:
        next_page_token = decision["nextPageToken"]
    except KeyError:
        next_page_token = None
    if next_page_token is None:
        return decision

    # Continue, we have a nextPageToken. Assemble a full array of events by continually polling
    all_events = decision["events"]
    while next_page_token is not None:
        try:
            next_page_token = decision["nextPageToken"]
            if next_page_token is not None:
                decision = conn.poll_for_decision_task(domain, task_list,
                                                       identity, maximum_page_size,
                                                       next_page_token)
                for event in decision["events"]:
                    all_events.append(event)
        except KeyError:
            next_page_token = None

    # Finally, reset the original decision response with the full set of events
    decision["events"] = all_events

    return decision

def get_input(decision):
    """
    From the decision response, which is JSON data form SWF, get the
    input data that started the workflow
    """
    try:
        input = json.loads(decision["events"][0]["workflowExecutionStartedEventAttributes"]["input"])
    except KeyError:
        input = None
    return input

def get_taskToken(decision):
    """
    Given a response from polling for decision from SWF via boto,
    extract the taskToken from the json data, if present
    """
    try:
        return decision["taskToken"]
    except KeyError:
        # No taskToken returned
        return None

def get_workflowType(decision):
    """
    Given a polling for decision response from SWF via boto,
    extract the workflowType from the json data
    """
    try:
        return decision["workflowType"]["name"]
    except KeyError:
        # No workflowType found
        return None

def get_workflow_name(workflowType):
    """
    Given a workflowType, return the name of a
    corresponding workflow class to load
    """
    return "workflow_" + workflowType

def import_workflow_class(workflow_name):
    """
    Given an workflow subclass name as workflow_name,
    attempt to lazy load the class when needed
    """
    try:
        module_name = "workflow." + workflow_name
        importlib.import_module(module_name)
        # Reload the module, in case it was imported before
        reload_module(module_name)
        return True
    except ImportError:
        return False

def reload_module(module_name):
    """
    Given an module name,
    attempt to reload the module
    """
    try:
        reload(eval(module_name))
    except NameError:
        pass

def get_workflow_object(workflow_name, settings, logger, conn, token, decision, maximum_page_size):
    """
    Given a workflow_name, and if the module class is already
    imported, create an object an return it
    """
    full_path = "workflow." + workflow_name + "." + workflow_name
    f = eval(full_path)
    # Create the object
    workflow_object = f(settings, logger, conn, token, decision, maximum_page_size)
    return workflow_object


if __name__ == "__main__":

    ENV = None
    forks = None

    # Add options
    parser = OptionParser()
    parser.add_option("-e", "--env", default="dev", action="store", type="string",
                      dest="env", help="set the environment to run, either dev or live")
    (options, args) = parser.parse_args()
    if options.env:
        ENV = options.env
    process.monitor_interrupt(lambda flag: decide(ENV, flag))
