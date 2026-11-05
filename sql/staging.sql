-- Вьюхи над исходными файлами. Очистка возраста и обрезка дат по CUTOFF - в витрине признаков.
-- Пути и сдвиг приходят из Python в переменных train_csv, clients_csv, purchases_parquet, clients_tz_shift.

create or replace view uplift_train as
select * from read_csv(getvariable('train_csv'));

create or replace view clients_raw as
select * from read_csv(getvariable('clients_csv'));

-- Даты clients на clients_tz_shift часов позже, чем в purchases (sql/quality.sql, clients_time_offset).
create or replace view clients as
select
    client_id,
    first_issue_date - to_hours(getvariable('clients_tz_shift')) as first_issue_date,
    first_redeem_date - to_hours(getvariable('clients_tz_shift')) as first_redeem_date,
    age,
    gender
from clients_raw;

create or replace view purchases as
select * from read_parquet(getvariable('purchases_parquet'));
