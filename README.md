# auto-SNVPhyl
## Installation
```console
pip install bioblend
git clone https://github.com/devonpmack/auto-SNVPhyl.git
```
## Generating API Keys
### Redmine
You can find your API key on your account page ( /my/account ) when logged in, on the right-hand pane of the default layout.
### Galaxy
First login, then go to User>API Keys>Generate a New Key Now

## Setup and configuration
```console
python3 server_runner.py
```
Run the program and it will ask you for all the configuration it needs.
- api_key: your API key for Galaxy (generated above)
- ip: IP to Galaxy (copy paste the url from your browser, currently http://192.168.1.3:48888/
- nasmnt: path to the NAS
- workflow ID: The workflow ID of SNVPhyl, currently f2db41e1fa331b3e
- max_histories: The max amount of histories allowed on galaxy before the program will clear space.
- seconds_between_redmine_checks: How many seconds to wait between checks on redmine looking for new SNVPhyls to run

## Running a SNVPhyl without Redmine, just using terminal
First fill in retrieve.txt with all the fastq SEQ-ID's that you want to compare your reference to
Next run the script using -r REFERENCE-SEQ-ID
```console
python3 -r REFERENCE-SEQ-ID
```
Usage:
main.py [-h] [-r REFERENCE] [-e] [-n HISTORY_NAME] [-m]

optional arguments:
- -h show help message and exit
- -r REFERENCE Input the seqid of the reference file. Also tells the program to extract the fastqs in your retrieve.txt. If              this parameter is not given then it will use the files in your upload folder, it will autodetect the reference file as long as it's a fasta.
- --noextract Use if you don't want any fastq files to be extracted from the nas, so only use files in your upload folder.
- -n HISTORY_NAME Name of the history to create
- -m Use the files in your upload directory (can use this in addition to the files extracted). If this flag is not used then it will clear the files in your upload directory.
