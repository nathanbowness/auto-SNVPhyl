# auto-SNVPhyl
## Installation
```console
git clone https://github.com/devonpmack/auto-SNVPhyl.git
python3 setup.py install
```
## Generating API Keys
### Redmine
You can find your API key on your account page ( /my/account ) when logged in, on the right-hand pane of the default layout.
### Galaxy
First login, then go to User>API Keys>Generate a New Key Now

## Configuring auto-SNVPhyl
First run the Redmine listener:
```console
python3 server_runner.py
```
Enter your Redmine API Key (generated above).
It will now ask you for all the configuration options/requirements:
- api_key: Your Galaxy API key (generated above).
- ip: The URL of Galaxy.
- max_histories: The max number of histories allowed on galaxy before it will clear space
- nasmnt: The directory of the nas on your system
- seconds_between_redmine_checks": How many seconds to wait before making another check to redmine for new SNVPhyl requests.
- workflow_id: The ID of the SNVPhyl workflow, leave this as default.

Now the program is running!

## Running just a SNVPhyl without redmine
First enter all the SEQ-IDS you want to compare the reference to into "retrieve.txt". Now run the SNVPhyl with `python3 main.py -r REFERENCE_SEQ_ID`. There are a lot of options which you can see with `python3 main.py -h`. For example if you want to input your own files into the SNVPhyl use `python3 main.py --manual --noextract`.