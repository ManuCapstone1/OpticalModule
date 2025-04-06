import paramiko
import os
import re

class RaspberryPiTransfer:
    """
    Handles SFTP and SSH-based communication with a Raspberry Pi,
    including transfering files within folders, and emptying folders on
    Raspberry Pi
    """

    def __init__(self):
        """
        Initialize with Raspberry Pi credentials.
        """

        self.host = "192.168.1.111"
        self.username = "microscope"
        self.password = "microscope"
        self.transport = None
        self.sftp = None
        self.ssh_client = None 

    def connect_sftp(self):
        """
        Establish an SFTP connection to the Raspberry Pi.

        Raises:
            Exception: If the connection fails.
        """
        try:
            self.transport = paramiko.Transport((self.host, 22))
            self.transport.connect(username=self.username, password=self.password)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            print(f"Successfully connected to {self.host} for SFTP operations")
        except Exception as e:
            print(f"Error connecting to Raspberry Pi for SFTP: {e}")
            raise

    def connect_ssh(self):
        """
        Establish an SSH connection to the Raspberry Pi.

        Raises:
            Exception: If the connection fails.
        """
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Automatically add host keys
            self.ssh_client.connect(self.host, username=self.username, password=self.password)
            print(f"Successfully connected to {self.host} for SSH operations")
        except Exception as e:
            print(f"Error connecting to Raspberry Pi for SSH: {e}")
            raise
    
    def transfer_folder(self, remote_folder, local_folder, new_filename=False):
        """
        Transfer all files from a remote Raspberry Pi folder to a local folder using SFTP.

        Args:
            remote_folder (str): Path to the folder on the Raspberry Pi.
            local_folder (str): Path to the folder on the local machine (PC).
            new_filename (bool): If True, rename files by removing the second numeric group
                                 (e.g., '001_02_image.png' → '001_image.png').
        """
        
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)

        try:
            # Get list of files in the remote folder
            remote_files = self.sftp.listdir(remote_folder)
            if not remote_files:
                print("No files found in remote directory.")
                return

            for filename in remote_files:
                remote_file_path = os.path.join(remote_folder, filename)

                # If new_filename is True, rename the file by removing the second number
                # File renaming is used for scanning operation for ImageJ macro
                if new_filename:
                    filename = re.sub(r'^(\d+)_\d+_(.*)$', r'\1_\2', filename)

                local_file_path = os.path.join(local_folder, filename)

                try:
                    print(f"Downloading: {filename}")
                    self.sftp.get(remote_file_path.replace('\\', '/'), local_file_path)
                    print(f"Successfully downloaded {filename}")
                except FileNotFoundError:
                    print(f"File not found: {remote_file_path}")
                except Exception as e:
                    print(f"Error downloading {filename}: {e}")

        except Exception as e:
            print(f"Error accessing remote directory: {e}")



    def empty_folder(self, remote_folder):
        """
        Delete all files and subdirectories in a remote folder using SSH.

        Args:
            remote_folder (str): Path to the remote folder to be cleared.
        """
        try:
            # Use SSH to remove all files and directories in the remote folder
            print(f"Attempting to empty folder: {remote_folder}")
            stdin, stdout, stderr = self.ssh_client.exec_command(f"rm -rf {remote_folder}/*")  # Remove all files and subdirectories

            # Read output and errors
            err = stderr.read().decode()
            if err:
                print(f"Error emptying folder: {err}")
            else:
                print(f"Successfully emptied folder: {remote_folder}")
        except Exception as e:
            print(f"Error emptying folder: {e}")

    def close_sftp_connection(self):
        """
        Close the SFTP connection.
        """
        if self.sftp:
            self.sftp.close()
        if self.transport:
            self.transport.close()
        print("SFTP connection closed.")

    def close_ssh_connection(self):
        """
        Close the SSH connection.
        """
        if self.ssh_client:
            self.ssh_client.close()
        print("SSH connection closed.")
