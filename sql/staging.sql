-- Вьюхи над исходными файлами без изменений. Очистка (возраст, даты после CUTOFF) - в витрине признаков.
-- Пути приходят из Python в переменных train_csv, clients_csv, purchases_parquet.

create or replace view uplift_train as
select * from read_csv(getvariable('train_csv'));

create or replace view clients as
select * from read_csv(getvariable('clients_csv'));

create or replace view purchases as
select * from read_parquet(getvariable('purchases_parquet'));
