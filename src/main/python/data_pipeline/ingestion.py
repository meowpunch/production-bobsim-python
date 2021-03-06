import functools

import pandas as pd

from utils.general import load_csv, load_file_list
from utils.s3 import save_to_s3, list_objects, get_url_s3, save_json

# TODO: All will be changed


def save_csv(filename):
    """
        TODO: check already saved files and not overwrite

        1. delete korean in filename
        2. get year and make key(dir)
    :param filename: e.g. '원천조사가격정보_201501.csv'
    :return: e.g. '201501.csv
    """
    new = filename[9:]
    """
    # about partitioning
    year = new[:4]
    key = 'price-predictor/origin/csv/' + year + '/' + new
    """

    key = 'price-predictor/origin/csv/' + new
    save_to_s3(key=key, body=load_csv(filename))
    return new


def origin_bucket_csv():
    """
        save local csv to s3
    :return: list of changed file names.
    """
    file_list = load_file_list(directory='csv')
    new_list = list(map(save_csv, file_list))
    return print("success save all ", new_list)


def func(filename, path, prefix):
    print(path + filename)
    df = pd.read_csv(path + '/' + filename, encoding='euc-kr')
    save_json(directory=prefix.replace("csv", "json"),
              filename=filename.replace(".csv", ""),
              data=df.to_dict())
    return filename


def origin_bucket_json():
    """
        # TODO: openAPI
        1. using openAPI from public & csv from s3
        2. combine data by json per year.
        2. save json to s3
    :return:
    """
    prefix = 'price-predictor/origin/csv'
    objs = list_objects(prefix=prefix)
    file_list = list(map(lambda x: x.key[len(prefix) + 1:], objs))[1:]

    destination_url = get_url_s3() + "/" + prefix
    list(map(functools.partial(func,
                               path=destination_url,
                               prefix=prefix), file_list))


if __name__ == '__main__':
    # TODO: implement for openAPI
    # origin_bucket_csv()
    origin_bucket_json()
