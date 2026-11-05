-- 在 TiDB Cloud 上建库建表（结构与本地 MySQL 一致；索引等数据导入后再建，导入更快）
CREATE DATABASE IF NOT EXISTS taobao;
USE taobao;

DROP TABLE IF EXISTS ub;
CREATE TABLE ub (
  user_id       INT UNSIGNED NOT NULL,
  item_id       INT UNSIGNED NOT NULL,
  category_id   INT UNSIGNED NOT NULL,
  behavior_type VARCHAR(8)   NOT NULL,
  ts            BIGINT       NOT NULL,
  dt            DATETIME     NOT NULL,
  d             DATE         NOT NULL,
  h             TINYINT      NOT NULL
) DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_bin;

DROP TABLE IF EXISTS user_rfm;
CREATE TABLE user_rfm (
  user_id        INT UNSIGNED NOT NULL,
  recency_days   INT,
  frequency      BIGINT NOT NULL DEFAULT 0,
  monetary_proxy BIGINT NOT NULL DEFAULT 0,
  r_high         INT,
  f_high         INT,
  m_high         INT,
  segment        VARCHAR(6) NOT NULL DEFAULT ''
) DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_bin;
