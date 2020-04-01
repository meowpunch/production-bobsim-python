from io import StringIO

import numpy as np
import pandas as pd

from data_pipeline.dtype import dtype
from util.logging import init_logger
from util.s3_manager.manager import S3Manager


class OpenDataRawMaterialPrice:

    def __init__(self, date: str):
        self.logger = init_logger()

        # s3
        self.bucket_name = "production-bobsim"
        self.load_key = "public_data/open_data_raw_material_price/origin/csv/{filename}.csv".format(
            filename=date
        )
        self.save_key = "public_data/open_data_raw_material_price/process/csv/{filename}.csv".format(
            filename=date
        )

        self.dtypes = dtype["raw_material_price"]

        # load filtered df
        self.input_df = self.load()

    def load(self):
        """
            fetch DataFrame and check validate
        :return: pd DataFrame
        """
        # fetch
        manager = S3Manager(bucket_name=self.bucket_name)
        df = manager.fetch_objects(key=self.load_key)

        # TODO: no use index to get first element.
        # validate (filter by column and check types)
        return df[0][self.dtypes.keys()].astype(dtype=self.dtypes)

    def save(self, df: pd.DataFrame):
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        manager = S3Manager(bucket_name=self.bucket_name)
        manager.save_object(body=csv_buffer.getvalue().encode('euc-kr'), key=self.save_key)

    def clean(self, df: pd.DataFrame):
        """
            clean null value
        :return: cleaned DataFrame
        """
        # pd Series represents the number of null values by column
        df_null = df.isna().sum()

        if df_null.sum() > 0:
            filtered = df_null[df_null.map(lambda x: x > 0)]
            self.logger.info(filtered)

            # drop rows have null values.
            return df.dropna(axis=0)
        else:
            self.logger.info("no missing value at raw material price")
            return df

    @staticmethod
    def transform_by_skew(df: pd.DataFrame):
        """
            get skew by numeric columns and log by skew
        :param df: cleaned pd DataFrame
        :return: transformed pd DataFrame
        """
        # get skew
        skew_feature = df["당일조사가격"].skew()
        # log by skew
        # TODO: define threshold not just '1'
        if abs(skew_feature) > 1:
            skewed_df = df.assign(당일조사가격=np.log1p(df["당일조사가격"]))
            return skewed_df
        else:
            return df

    @staticmethod
    def combine_categories(df: pd.DataFrame):
        """
            combine 4 categories into one category 'item name'
        :return: combined pd DataFrame
        """
        return df.assign(
            품목명=lambda x: x.표준품목명 + x.조사가격품목명 + x.표준품종명 + x.조사가격품종명
        ).drop(columns=["표준품목명", "조사가격품목명", "표준품종명", "조사가격품종명"], axis=1)

    @staticmethod
    def get_unit(unit_name):
        return {
            '20KG': 200, '1.2KG': 12, '8KG': 80, '5KG': 5, '2KG': 2, '1KG': 10, '1KG(단)': 10, '1KG(1단)': 10,
            '600G': 6, '500G': 5, '200G': 2, '100G': 1,
            '10마리': 10, '5마리': 5, '2마리': 2, '1마리': 1,
            '30개': 10, '10개': 10, '1개': 1,
            '1L': 10,
            '1속': 1,
            # TODO: handle no supported unit
        }.get(unit_name, 1)

    def convert_by_unit(self, df: pd.DataFrame):
        """
            transform unit
        :return: transformed pd DataFrame
        """
        return df.assign(
            조사단위명=lambda r: r.조사단위명.map(
                lambda x: self.get_unit(x)
            )
        ).assign(
            당일조사가격=lambda x: x.당일조사가격 / x.조사단위명
        ).drop("조사단위명", axis=1)

    def filter(self, df):
        """
            ready to process
        :param df: self.input_df
        :return: filtered pd DataFrame
        """
        # only retail price
        retail = df[df.조사구분명 == "소비자가격"].drop("조사구분명", axis=1)

        # combine 4 categories into one
        combined = self.combine_categories(retail)

        # prices divided by 'material grade'(조사등급명) will be used on average.
        aggregated = combined.drop("조사등급명", axis=1).groupby(
            ["조사일자", "조사지역명", "조사단위명", "품목명"]
        ).mean().reset_index()

        # convert prices in standard unit
        return self.convert_by_unit(aggregated)

    def process(self):
        """
            process
                1. filter
                2. clean null value
                3. transform as distribution of data
                4. add 'season' and 'is_weekend" column

                5. save processed data to s3
            TODO: save to rdb
        :return: exit code (bool)  0:success 1:fail
        """
        try:
            filtered = self.filter(self.input_df)
            cleaned = self.clean(filtered)
            transformed = self.transform_by_skew(cleaned)
            decomposed = self.decompose_date(transformed)

            self.save(decomposed)
        except Exception as e:
            # TODO: consider that it can repeat to save one more time
            self.logger.critical(e, exc_info=True)
            return 1

        self.logger.info("success to process raw material price")
        return 0

    @staticmethod
    def decompose_date(df: pd.DataFrame):
        # add is_weekend & season column
        return df.assign(
            is_weekend=lambda x: x.조사일자.dt.dayofweek.apply(
                lambda day: 1 if day > 4 else 0
            ),
            season=lambda x: x.조사일자.dt.month.apply(
                lambda month: (month % 12 + 3) // 3
            )
        )



