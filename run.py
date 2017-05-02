class Run(object):
    def main(self):
        pass

    def __init__(self, args):
        AutoSNVPhyl(args)

if __name__ == "__main__":
    from main import AutoSNVPhyl
    import sys
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--reference",
                        help="Input the seqid of the reference file. "
                             "Also tells the program to extract the fastqs in your retrieve.txt. "
                             "If this parameter is not given then it will use the files in your "
                             "upload folder, it will autodetect the reference file as long as it's"
                             "a fasta. ", type=str)
    parser.add_argument("-e", "--noextract", action="store_true",
                        help="Use if you don't want your fastq files to be extracted and only want the ones in upload")
    parser.add_argument("-n", "--history_name", type=str,
                        help="Name of the history to create")
    parser.add_argument("-i", "--redmine", type=int,
                        help="Set a redmine ticket id to put the lists in")
    parser.add_argument("-m", "--manual", action="store_true",
                        help="Use the files in your upload directory (can use this in addition to the files extracted)."
                             "If this flag is not used then it will clear the files in your upload directory.")
    args = parser.parse_args()

    Run(args)
