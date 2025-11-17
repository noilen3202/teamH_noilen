-- db/add_image_column.sql
-- Recruitmentsテーブルに画像ファイル名保存用のカラムを追加します。

ALTER TABLE Recruitments
ADD COLUMN image_filename VARCHAR(255) NULL COMMENT '募集に関連する画像ファイル名';