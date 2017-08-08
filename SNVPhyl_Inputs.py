import re


class Inputs(object):
    def __init__(self, issue):
        self.reference = None
        self.fastqs = list()
        self.name = issue.id
        self.rename = {}

        self.parse_description(issue.description)

    def parse_description(self, description):

        mode = 'none'
        regex = r"^(2\d{3}-\w{2,10}-\d{3,4}|\d{2}-\d{4})$"  # Match xxxx-xxx-xxxx or xx-xxxx

        # Turn the description into a list of lines
        input_list = description.split('\n')
        # Get rid of \r
        input_list = map(str.strip, input_list)

        for line in input_list:
            # Check for mode changes
            if line.lower().startswith('reference') and len(line) < len('reference') + 3:
                mode = 'ref'
                continue
            elif line.lower().startswith('compare') and len(line) < len('compare') + 3:
                mode = 'comp'
                continue
            elif line.lower() == '':
                # Blank line
                mode = 'none'
                continue

            if self.reference is not None and len(self.fastqs) > 0 and mode == 'none':
                # Finished gathering all input
                break

            # Get seq-id
            if mode == 'ref':
                if re.match(regex, line):
                    self.reference = line
                else:
                    raise ValueError("Invalid seq-id \"%s\"" % line)
            elif mode == 'comp':
                if re.match(regex, line):
                    self.fastqs.append(line)
                else:
                    pass
                    raise ValueError("Invalid seq-id \"%s\"" % line)

        # Check for duplicates
        l = self.fastqs
        duplicates = set([x for x in l if l.count(x) > 1])
        if len(duplicates) > 0:
            msg = "Duplicate SEQ-IDs!\n"
            for duplicate in duplicates:
                msg += duplicate + '\n'
            raise ValueError(msg)

        if self.reference is None or len(self.fastqs) < 1:
            raise ValueError("Invalid format for redmine request.")

    def add_renaming_dict(self, rename_set):
        self.rename = rename_set
