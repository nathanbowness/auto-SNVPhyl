# auto-SNVPhyl
## Installation
```console
git clone https://github.com/devonpmack/auto-SNVPhyl.git
pip install requirements.txt
```
## Generating API Keys
### Redmine
You can find your API key on your account page ( /my/account ) when logged in, on the right-hand pane of the default layout.
### Galaxy
First login, then go to User>API Keys>Generate a New Key Now

## Setup and configuration
Run the program and it will ask you for all the configuration it needs.
```console
python3 server_runner.py
```
It will now ask you for all the configuration options/requirements:
- api_key: your API key for Galaxy (generated above)
- ip: The URL of Galaxy (copy paste the url from your browser, currently http://192.168.1.3:48888/)
- nasmnt: path to the NAS
- workflow ID: The workflow ID of SNVPhyl, leave this as default.
- max_histories: The max amount of histories allowed on galaxy before the program will clear space.
- seconds_between_redmine_checks: How many seconds to wait between checks on redmine looking for new SNVPhyls to run

Finally enter your Redmine API Key (generated above).
### Running the Redmine Listener permanently
First install the supervisor package
```console
sudo apt-get install supervisor
```
Create a config file for your daemon at /etc/supervisor/conf.d/auto_snvphyl.conf
```
[program:auto_snvphyl]
directory=/path/to/project/root
environment=ENV_VARIABLE=example,OTHER_ENV_VARIABLE=example2
command=python3 server_runner.py -f
autostart=true
autorestart=true
```
Restart supervisor to load your new .conf
```
supervisorctl update
supervisorctl restart auto_snvphyl
```
## Running a SNVPhyl without Redmine, just using terminal
First enter all the SEQ-IDS you want to compare the reference to into "retrieve.txt".
Now run the SNVPhyl with
```console
python3 -r REFERENCE-SEQ-ID
```
There are a lot of options, for example if you want to input your own files into the SNVPhyl use
```console
python3 main.py --manual --noextract
```
Arguments:
- -h show help message and exit
- -r REFERENCE Input the seqid of the reference file. Also tells the program to extract the fastqs in your retrieve.txt. If              this parameter is not given then it will use the files in your upload folder, it will autodetect the reference file as long as it's a fasta.
- --noextract Use if you don't want any fastq files to be extracted from the nas, so only use files in your upload folder.
- -n HISTORY_NAME Name of the history to create
- --manual Use the files in your upload directory (can use this in addition to the files extracted). If this flag is not used then it will clear the files in your upload directory.
