import os
import glob

if __name__=="__main__":
    # 1. List XML files that start with "combined".
    pattern = "combined*.xml"
    # combined_files = glob.glob(f"static/bitcoin-dev/**/{pattern}")
    combined_files = glob.glob(f"static/lightning-dev/**/{pattern}")
    print(len(combined_files))

    # 2. Delete the files from their existing location.
    for file in combined_files:
        try:
            os.remove(file)
            print(f"Deleted file: {file}")
        except OSError as e:
            print(f"Error deleting the file {file}: {e}")
