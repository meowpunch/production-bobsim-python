import tempfile

import pandas as pd
from joblib import dump
import numpy as np
from sklearn.linear_model import ElasticNet
from sklearn.metrics import make_scorer, mean_squared_error
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

from analysis.hit_ratio_error import hit_ratio_error
from utils.logging import init_logger
from utils.s3_manager.manage import S3Manager
from utils.visualize import draw_hist


class ElasticNetModel:
    """
        ElasticNet
    """

    def __init__(self, bucket_name: str, x_train, y_train, params=None):
        # logger
        self.logger = init_logger()

        # s3
        self.s3_manager = S3Manager(bucket_name=bucket_name)

        if params is None:
            self.model = ElasticNet()
        else:
            self.model = ElasticNet(**params)

        self.x_train, self.y_train = x_train, y_train

        self.error = None
        self.metric = None

    def fit(self):
        self.model.fit(self.x_train, self.y_train)

    def predict(self, X):
        return self.model.predict(X=X)

    def estimate_metric(self, scorer, y, predictions):
        self.error = pd.Series(y - predictions, name="error")
        self.metric = scorer(y_true=y, y_pred=predictions)
        return self.metric

    def score(self):
        return self.model.score(self.x_train, self.y_train)

    @property
    def coef_df(self):
        """
        :return: pd DataFrame
        """
        return pd.Series(
            data=np.append(self.model.coef_, self.model.intercept_),
            index=self.x_train.columns.tolist() + ["intercept"],
        ).rename("beta").reset_index().rename(columns={"index": "column"})

    def save(self, prefix):
        """
            save beta coef, metric, distribution, model
        :param prefix: dir
        """
        self.save_coef(key="{prefix}/beta.csv".format(prefix=prefix))
        self.save_metric(key="{prefix}/metric.pkl".format(prefix=prefix))
        self.save_error_distribution(prefix=prefix)
        self.save_model(key="{prefix}/model.pkl".format(prefix=prefix))

    def save_coef(self, key):
        self.logger.info("coef:\n{coef}".format(coef=self.coef_df))
        self.s3_manager.save_df_to_csv(self.coef_df, key=key)

    def save_metric(self, key):
        self.logger.info("customized RMSE is {metric}".format(metric=self.metric))
        self.s3_manager.save_dump(x=self.metric, key=key)

    def save_model(self, key):
        self.s3_manager.save_dump(self.model, key=key)

    def save_error_distribution(self, prefix):
        draw_hist(self.error)
        self.s3_manager.save_plt_to_png(
            key="{prefix}/image/error_distribution.png".format(prefix=prefix)
        )

        ratio = hit_ratio_error(self.error)
        self.s3_manager.save_plt_to_png(
            key="{prefix}/image/hit_ratio_error.png".format(prefix=prefix)
        )
        return ratio


class ElasticNetSearcher(GridSearchCV):
    """
        for research
    """

    def __init__(
            self, x_train, y_train, bucket_name,
            grid_params=None, score=mean_squared_error
    ):
        if grid_params is None:
            grid_params = {
                "max_iter": [1, 5, 10],
                "alpha": [0, 0.0001, 0.001, 0.01, 0.1, 1, 10, 100],
                "l1_ratio": np.arange(0.0, 1.0, 0.1)
            }

        self.x_train = x_train
        self.y_train = y_train
        self.scorer = score

        self.error = None  # pd.Series
        self.metric = None

        # s3
        self.s3_manager = S3Manager(bucket_name=bucket_name)

        # logger
        self.logger = init_logger()

        super().__init__(
            estimator=ElasticNet(),
            param_grid=grid_params,
            scoring=make_scorer(self.scorer, greater_is_better=False),
            # we have to know the relationship before and after obviously, so n_splits: 2
            cv=TimeSeriesSplit(n_splits=2).split(self.x_train)
        )

    def fit(self, X=None, y=None, groups=None, **fit_params):
        super().fit(X=self.x_train, y=self.y_train)

    @property
    def coef_df(self):
        """
        :return: pd DataFrame
        """
        return pd.Series(
            data=np.append(self.best_estimator_.coef_, self.best_estimator_.intercept_),
            index=self.x_train.columns.tolist() + ["intercept"],
        ).rename("beta").reset_index().rename(columns={"index": "column"})

    def estimate_metric(self, y_true, y_pred):
        self.error = pd.Series(y_true - y_pred, name="error")
        self.metric = self.scorer(y_true=y_true, y_pred=y_pred)
        return self.metric

    def save(self, prefix):
        """
            save tuned params, beta coef, metric, distribution, model
        :param prefix: dir
        """
        self.save_params(key="{prefix}/params.pkl".format(prefix=prefix))
        self.save_coef(key="{prefix}/beta.pkl".format(prefix=prefix))
        self.save_metric(key="{prefix}/metric.pkl".format(prefix=prefix))
        self.save_error_distribution(prefix=prefix)
        self.save_model(key="{prefix}/model.pkl".format(prefix=prefix))

    def save_params(self, key):
        self.logger.info("tuned params: {params}".format(params=self.best_params_))
        self.s3_manager.save_dump(x=self.best_params_, key=key)

    def save_coef(self, key):
        self.logger.info("beta_coef:\n{coef}".format(coef=self.coef_df))
        self.s3_manager.save_df_to_csv(self.coef_df, key=key)

    def save_metric(self, key):
        self.logger.info("customized RMSE is {metric}".format(metric=self.metric))
        self.s3_manager.save_dump(x=self.metric, key=key)

    def save_model(self, key):
        # save best elastic net
        self.s3_manager.save_dump(self.best_estimator_, key=key)

    def save_error_distribution(self, prefix):
        draw_hist(self.error)
        self.s3_manager.save_plt_to_png(
            key="{prefix}/image/error_distribution.png".format(prefix=prefix)
        )

        ratio = hit_ratio_error(self.error)
        self.s3_manager.save_plt_to_png(
            key="{prefix}/image/hit_ratio_error.png".format(prefix=prefix)
        )
        return ratio
