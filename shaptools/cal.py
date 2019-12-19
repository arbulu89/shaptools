"""
SAP CAL (Cloud Application Library) management module

:author: xarbulu
:organization: SUSE LLC
:contact: xarbulu@suse.com

:since: 2019-12-19
"""

import logging
import subprocess
import shlex
import threading

# python2 compatibility (this code needs to be executed with salt py2 version)
try:
    import queue
except ImportError:
    import Queue
    queue = Queue

from shaptools import shell


class CalExecutionError(Exception):
    """
    CAL execution error
    """


class CalInstance(object):
    """
    SAP CAL instance
    """

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def is_installed(
            software_path, root_user, root_password):
        """
        Check if SAP CAL instance is installed

        Args:
            software_path (str): Path where the CAL installer is located
            root_user (str): Root user name
            root_password (str): Root user password
        """

        logger = logging.getLogger(__name__)

        cmd = 'bash {path}/install.sh'.format(path=software_path)
        cmd = shell.format_su_cmd(cmd, root_user)
        proc = subprocess.Popen(
            shlex.split(cmd), universal_newlines=False,
            stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        proc.stdin.write('{}\n'.format(root_password).encode())
        proc.stdin.flush()
        for line in iter(proc.stdout.readline, b''):
            logger.info(line)
            if 'Hit enter to continue otherwise use' in str(line):
                return True
        return False


    @staticmethod
    def install(
            software_path, sid_adm_password, root_user, root_password, force=False):
        """
        Install SAP CAL instance

        Args:
            software_path (str): Path where the CAL installer is located
            sid_adm_password (str): sidadm user password (minimum 8 chars)
            root_user (str): Root user name
            root_password (str): Root user password
            force (bool): Run the installation even an instance is already installed
        """

        def enqueue_output(out, input_queue, logger):
            """
            Enqueue stdout messages
            """
            for line in iter(out.readline, b''):
                logger.info(str(line))
                input_queue.put(str(line))

        def get_last_line(input_queue):
            """
            Get last line
            """
            last_line = ''
            while True:
                try:
                    last_line = input_queue.get(timeout=5)
                except queue.Empty:
                    break
            return last_line

        def answer(stdin, msg):
            """
            Answer the command question
            """
            stdin.write(msg.encode())
            stdin.flush()

        logger = logging.getLogger(__name__)

        cmd = 'bash {path}/install.sh'.format(path=software_path)
        cmd = shell.format_su_cmd(cmd, root_user)
        proc = subprocess.Popen(
            shlex.split(cmd), universal_newlines=False,
            stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        input_queue = queue.Queue()

        input_thread = threading.Thread(
            target=enqueue_output, args=(proc.stdout, input_queue, logger))
        input_thread.daemon = True
        input_thread.start()

        last_line = get_last_line(input_queue)

        # This means that the password is required (we cannot retrieve the password prompt)
        if last_line == '':
            answer(proc.stdin, '{}\n'.format(root_password))
            last_line = get_last_line(input_queue)

        if 'Hit enter to continue otherwise use' in last_line:
            if not force:
                raise CalExecutionError('A SAP system is already installed')
            else:
                answer(proc.stdin, '\n')
                last_line = get_last_line(input_queue)

        if 'Do you agree to the above license terms' not in last_line:
            raise CalExecutionError('Not expected message received')

        answer(proc.stdin, 'yes\n')

        last_line = get_last_line(input_queue)
        if 'Please enter a password' not in last_line:
            raise CalExecutionError('Not expected message received')
        answer(proc.stdin, '{}\n'.format(sid_adm_password))

        last_line = get_last_line(input_queue)
        if 'Please re-enter password for verification' not in last_line:
            raise CalExecutionError('Not expected message received')
        answer(proc.stdin, '{}\n'.format(sid_adm_password))

        last_line = get_last_line(input_queue)

        proc.communicate()
        if proc.returncode:
            raise CalExecutionError(
                'Installation failed. Find the installation logs in sapinst.log file')
