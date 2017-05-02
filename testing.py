from sequence_getter import SequenceGetter

a = SequenceGetter("test", "/mnt/nas/", output=True)

a.retrieve_file("2017-OLF-0092", "fastq_R2")

