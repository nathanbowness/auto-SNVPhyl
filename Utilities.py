import os


class CustomValues:
    # none
    max_histories = 6
    workflow_id = "f2db41e1fa331b3e"
    snvphyl_ip = "http://192.168.1.3:48888/"


class CustomKeys:

    # Config Json Keys
    max_histories = 'max_histories'
    workflow_id = 'workflow_id'
    snvpyhl_ip = 'ip'
    snvphyl_api_key = 'api_key'


class UtilityMethods:
    @staticmethod
    def create_dir(basepath, path_ext=""):
        """ Creates the the output directory if it doesn't exist """
        if not os.path.exists(os.path.join(basepath, path_ext)):
            os.makedirs(os.path.join(basepath, path_ext))