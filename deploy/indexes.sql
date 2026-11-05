-- 数据导入后再建索引（与本地一致，含为 DAU 查询加的覆盖索引 idx_d_user）
USE taobao;
CREATE INDEX idx_user_dt   ON ub (user_id, dt);
CREATE INDEX idx_user_item ON ub (user_id, item_id, behavior_type, ts);
CREATE INDEX idx_d_type    ON ub (d, behavior_type);
CREATE INDEX idx_cat_type  ON ub (category_id, behavior_type);
CREATE INDEX idx_d_user    ON ub (d, user_id);
