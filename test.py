from main import AutoSNVPhylError

try:
    raise AutoSNVPhylError("heyodawg")
except Exception as e:
    import traceback

    print("Lul")

    if type(e) == AutoSNVPhylError or ValueError:
        msg = str(e)
    else:
        msg = traceback.format_exc()

    print(msg)
