from RedmineAPI.Utilities import FileExtension, create_time_log
from RedmineAPI.Access import RedmineAccess
from RedmineAPI.Configuration import Setup
from Utilities import CustomKeys, CustomValues
from SNVPhyl_Inputs import Inputs

import os
from main import AutoSNVPhyl


class Run(object):
    def __init__(self, force):

        self.timelog = create_time_log(FileExtension.runner_log)

        # create a tuple dictionary for the custom terms to be set
        custom_terms = {CustomKeys.max_histories: (CustomValues.max_histories, True, int),
                        CustomKeys.workflow_id: (CustomValues.workflow_id, True, str),
                        CustomKeys.snvpyhl_ip: (CustomValues.snvphyl_ip, True, str),
                        CustomKeys.snvphyl_api_key: (None, True, str)}

        setup = Setup(time_log=self.timelog, custom_terms=custom_terms)
        setup.set_api_key(force)
        self.custom_values = setup.get_custom_term_values()

        # set the custom terms from the configuration to variables to be used
        self.max_histories = self.custom_values[CustomKeys.max_histories]
        self.workflow_id = self.custom_values[CustomKeys.workflow_id]
        self.snvphyl_ip = self.custom_values[CustomKeys.snvpyhl_ip]
        self.snvphyl_api_key = self.custom_values[CustomKeys.snvphyl_api_key]

        # set the default terms from configuration to be used
        self.seconds_between_checks = setup.seconds_between_check
        self.nas_mnt = setup.nas_mnt
        self.redmine_api_key = setup.api_key

        self.redmine_access = RedmineAccess(self.timelog, self.redmine_api_key)

        self.botmsg = '\n\n_I am a bot. This action was performed automatically._'
        self.issue_title = 'snvphyl'
        self.issue_status = 'In Progress'

    def timed_retrieve(self):
        import time
        while True:
            # Clear any entries on galaxy past the number selected by the user
            self.clear_space()

            # Get issues matching the issue status and title
            found_issues = self.redmine_access.retrieve_issues(self.issue_status, self.issue_title)
            # Respond to the issues in the list 1 at a time
            while len(found_issues) > 0:
                self.respond_to_issue(found_issues.pop(len(found_issues) - 1))
                self.clear_space()

            self.timelog.time_print("Waiting for the next check.")
            time.sleep(self.seconds_between_checks)

    def respond_to_issue(self, issue):
        self.timelog.time_print("Found SNVPhyl to run. Subject: %s. ID: %s" % (issue.subject, str(issue.id)))
        self.timelog.time_print("Adding to the list of responded to requests.")

        self.redmine_access.log_new_issue(issue)
        inputs = None
        error = False
        try:
            # from the description create an object to store variables from Redmine including:
            # 'Reference SEQID', a list of fastqs, Name of Project
            inputs = Inputs(issue)

            response = "Running SNVPhyl with reference %s\n\nComparing to:" % inputs.reference
            for fastq in list(inputs.fastqs):
                response += '\n' + fastq
            if inputs.reference not in inputs.fastqs:
                response += "Did you mean to not compare the reference to itself?"

        except ValueError as e:
            response = "Sorry, there was a problem with your SNVPhyl request:\n%s\n" \
                       "Please submit a new request and close this one." % e.args[0]
            error = True

        if not error:
            # Rename file'Invalid name to rename %s. Ignoring.'s if the rename.txt text file is include
            more_msg, rename_set = self.rename_files(issue)

            if inputs is None:
                error = True

            inputs.add_renaming_dict(rename_set)

            if more_msg is not None:
                response += '\n' + more_msg

        self.timelog.time_print('\n' + response)

        if error:  # If something went wrong set the status to feedback and assign the author the issue
            self.redmine_access.update_issue_to_author(issue, response+self.botmsg)
            return
        else:
            # Set the issue to in progress since the SNVPhyl is running
            self.redmine_access.update_status_inprogress(issue, response + self.botmsg)
            self.run_snvphyl(inputs, issue)

    def run_snvphyl(self, inputs, issue):
        # Parse input
        args = self.generate_args(inputs)
        # noinspection PyBroadException
        from main import AutoSNVPhylError
        try:
            runner = AutoSNVPhyl(args, inputs=inputs)
            result_path, file_error_msg = runner.run()
            # SNVPhyl finished, copy the zip to the NAS
            import shutil
            bio_request_folder = os.path.join(self.nas_mnt, 'bio_requests', str(issue.id))
            # Create folder with redmine id
            self.timelog.time_print("Creating directory %s" % bio_request_folder)
            if not os.path.exists(os.path.join(bio_request_folder)):
                os.makedirs(bio_request_folder)

            # Copy results to bio_request folder
            self.timelog.time_print("Copying %s to %s" % (result_path, bio_request_folder))
            shutil.copy(result_path, bio_request_folder)
            self.timelog.time_print("Completed Copying.")

            # Respond on redmine
            self.completed_response(result_path, issue, file_error_msg)

        except Exception as e:
            import traceback
            self.timelog.time_print("[Warning] AutoSNVPhyl had a problem, continuing redmine api anyways.")
            self.timelog.time_print("[AutoSNVPhyl Error Dump]\n" + traceback.format_exc())
            # Send response
            if type(e) == AutoSNVPhylError or ValueError:
                msg = str(e)
            else:
                msg = traceback.format_exc()

            # Assign the message back to the author
            message = "There was a problem with your SNVPhyl. Please create a new issue on " \
                      "Redmine to re-run it.\n%s" % msg
            self.redmine_access.update_issue_to_author(issue, message + self.botmsg)

    def completed_response(self, result_path, issue, file_error_msg):
        notes = file_error_msg
        file_name = "SNVPhyl_%s_Results.zip" % str(issue.id)

        from RedmineAPI.RedmineAPI import RedmineUploadError
        notes += "\n\nCompleted running SNVPhyl. Results stored at %s" % \
                 os.path.join("NAS/bio_requests/%s" % str(issue.id))
        try:
            self.redmine_access.redmine_api.upload_file(result_path, issue.id, 'application/zip',
                                                        file_name_once_uploaded=file_name)
        except RedmineUploadError:
            notes += "Couldn't upload your zip file to redmine. Results stored at %s" % \
                     os.path.join("NAS/bio_requests/%s" % str(issue.id))
            self.timelog.time_print("The file could not be uploaded to Redmine due to an error.")

        self.timelog.time_print("The zip file, %s was uploaded successfully to Redmine." % file_name)

        # Assign issue back to the author
        self.timelog.time_print("Assigning the issue back to the author.")
        self.redmine_access.update_issue_to_author(issue, notes+self.botmsg)
        self.timelog.time_print("Completed Response to issue %s." % str(issue.id))

    @staticmethod
    def generate_args(inputs):
        import argparse

        args = argparse.Namespace()
        args.reference = inputs.reference
        args.history_name = inputs.name
        args.noextract = False
        args.manual = False  # Change this to true if you want to manually run the snvphyl

        return args

    def clear_space(self):
        from bioblend.galaxy import GalaxyInstance
        from bioblend import ConnectionError
        gi = GalaxyInstance(self.snvphyl_ip, self.snvphyl_api_key)
        self.timelog.time_print("Clearing space on Galaxy")

        while True:
            try:
                available = gi.histories.get_histories()  # Ping galaxy
                break
            except ConnectionError as e:
                if e.status_code == 403:  # Invalid API key
                    self.timelog.time_print("You have entered a Invalid Galaxy API Key!")
                    self.timelog.time_print("Please rerun the program and re-enter the Galaxy API Key.")
                elif 'Max retries exceeded' in str(e.args[0]):
                    self.timelog.time_print("Error: Galaxy isn't running/connection error.")
                    self.timelog.time_print("Waiting 1 hour...")
                    import time
                    time.sleep(3600)
                else:
                    raise

        if len(available) >= self.max_histories:
            msg = 'Clearing data.'
        else:
            msg = 'Not clearing data.'

        self.timelog.time_print("Currently %d histories on Galaxy. %s" % (len(available), msg))
        while len(available) > self.max_histories:
            self.timelog.time_print("Deleting history %s to clear space..." % available.pop(len(available) - 1)['name'])
            try:
                gi.histories.delete_history(available[-1]['id'], purge=True)
            except ConnectionError as e:
                if e.status_code == 403:  # Invalid API key
                    self.timelog.time_print("Invalid Galaxy API Key!")
                    exit(1)
                elif 'Max retries exceeded' in str(e.args[0]):
                    self.timelog.time_print("Error: Galaxy isn't running/connection error.")
                    exit(1)
                else:
                    raise

        self.timelog.time_print("Finished clearing space")

    def rename_files(self, issue):

        rename_txt_file = self.redmine_access.get_attached_text_file(issue, 0)

        if rename_txt_file is None:
            return None, []

        import re
        regex = r'([^\t\n\r]+)(?:,|\n|\r|\t)([^\t\n\r]+)'  # Matches a list of comma separated pairs eg. seq,a,seq2,b
        pairs = re.findall(regex, rename_txt_file)

        if len(pairs) == 0:
            return 'Invalid rename.txt file.', []

        # Check its a good file
        ignore = []
        for pair in pairs:
            # Check duplicate
            for compare in pairs:
                if pair[0] == compare[0]:
                    if pair[1] != compare[1]:
                        return 'Not using rename.txt because of duplicate definition in the rename.txt file', []
                    # Otherwise let it go

            # Make sure its valid
            regex = r'.+'  # TODO actual regex
            if not re.fullmatch(regex, pair[1]):
                ignore.append(pair)

        # Feedback
        msg = "Renaming files before starting SNVPhyl."
        if len(ignore) > 0:
            msg += 'Some names were invalid and were ignored:\n'
            for out in ignore:
                msg += '\n%s' % out[1]

        # Convert to dict
        result = {}
        for pair in pairs:
            result[pair[0]] = pair[1]
        self.timelog.time_print(result)
        return msg, result
