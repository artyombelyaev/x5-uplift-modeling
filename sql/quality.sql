-- Этап 1: ключи, дубли, пропуски, аномалии, даты.
-- Чек - пара (client_id, transaction_id): 28 значений transaction_id встречаются у двух разных клиентов
-- (запрос transaction_id_collisions). Агрегаты по чекам - через CTE «одна строка на чек».

-- name: overview
select 'uplift_train' as tbl, count(*) as n_rows, count(distinct client_id) as n_clients from uplift_train
union all
select 'clients', count(*), count(distinct client_id) from clients
union all
select 'purchases', count(*), count(distinct client_id) from purchases;

-- name: purchases_keys
select
    count(distinct (client_id, transaction_id)) as n_transactions,
    count(distinct transaction_id) as n_transaction_ids,
    count(distinct store_id) as n_stores,
    count(distinct product_id) as n_products,
    min(transaction_datetime) as first_dt,
    max(transaction_datetime) as last_dt
from purchases;

-- name: nulls
select 'uplift_train' as tbl, * from (unpivot (select avg((columns(*) is null)::int) from uplift_train) on columns(*))
union all
select 'clients', * from (unpivot (select avg((columns(*) is null)::int) from clients) on columns(*))
union all
select 'purchases', * from (unpivot (select avg((columns(*) is null)::int) from purchases) on columns(*));

-- name: train_shares
select
    count(*) as n,
    avg(target) as target_share,
    avg(treatment_flg) as treatment_share,
    count(*) filter (where treatment_flg = 1 and target = 1) as t1_y1,
    count(*) filter (where treatment_flg = 1 and target = 0) as t1_y0,
    count(*) filter (where treatment_flg = 0 and target = 1) as t0_y1,
    count(*) filter (where treatment_flg = 0 and target = 0) as t0_y0
from uplift_train;

-- name: duplicates
select
    (select count(*) - count(distinct client_id) from uplift_train) as train_dup_client,
    (select count(*) - count(distinct client_id) from clients) as clients_dup_client,
    (select count(*) from purchases) - (select count(*) from (select distinct * from purchases)) as purchases_dup_rows,
    (select count(*) - count(distinct (client_id, transaction_id, product_id)) from purchases) as purchases_dup_line_key;

-- name: transaction_id_collisions
with t as (select distinct client_id, transaction_id from purchases)
select count(*) as n_transaction_ids, max(n_clients) as max_clients
from (select transaction_id, count(*) as n_clients from t group by 1 having count(*) > 1);

-- name: key_coverage
with p as (select distinct client_id from purchases)
select
    (select count(*) from uplift_train where client_id not in (select client_id from clients)) as train_not_in_clients,
    (select count(*) from uplift_train where client_id not in (select client_id from p)) as train_not_in_purchases,
    (select count(*) from p where client_id not in (select client_id from clients)) as purchases_not_in_clients,
    (select count(*) from clients where client_id not in (select client_id from p)) as clients_not_in_purchases;

-- name: transaction_consistency
-- Сколько чеков, где поле уровня чека принимает больше одного значения.
with trn as (
    select
        client_id,
        transaction_id,
        count(distinct transaction_datetime) as n_dt,
        count(distinct store_id) as n_store,
        count(distinct purchase_sum) as n_purchase_sum,
        count(distinct regular_points_received) as n_reg_received,
        count(distinct express_points_received) as n_exp_received,
        count(distinct regular_points_spent) as n_reg_spent,
        count(distinct express_points_spent) as n_exp_spent
    from purchases
    group by all
)
select
    count(*) as n_transactions,
    count(*) filter (where n_dt > 1) as dt,
    count(*) filter (where n_store > 1) as store_id,
    count(*) filter (where n_purchase_sum > 1) as purchase_sum,
    count(*) filter (where n_reg_received > 1) as regular_points_received,
    count(*) filter (where n_exp_received > 1) as express_points_received,
    count(*) filter (where n_reg_spent > 1) as regular_points_spent,
    count(*) filter (where n_exp_spent > 1) as express_points_spent
from trn;

-- name: purchase_sum_vs_lines
-- purchase_sum чека против сумм строк. trn_sum_from_iss в строке всегда целое, purchase_sum - с копейками,
-- поэтому «совпадает» - с точностью 0,5 руб. на строку. Отдельно чеки со списанием баллов и без.
with trn as (
    select
        client_id,
        transaction_id,
        any_value(purchase_sum) as purchase_sum,
        -any_value(regular_points_spent) - any_value(express_points_spent) as points_spent,
        sum(trn_sum_from_iss) as iss,
        sum(coalesce(trn_sum_from_red, 0)) as red,
        count(*) as n_lines,
        count(trn_sum_from_red) as n_red_lines
    from purchases
    group by all
)
select
    points_spent > 0 as has_points_spent,
    n_red_lines > 0 as has_red_lines,
    count(*) as n_transactions,
    avg((abs(purchase_sum - iss) <= 0.5 * n_lines)::int) as ps_eq_iss,
    avg((abs(purchase_sum - red) <= 0.5 * n_lines)::int) as ps_eq_red,
    avg((abs(red - iss - points_spent) <= 0.5 * n_lines)::int) as red_minus_iss_eq_points_spent,
    avg((n_red_lines = n_lines)::int) as all_lines_have_red
from trn
group by all
order by all;

-- name: line_values
select
    count(*) as n_lines,
    count(*) filter (where trn_sum_from_iss <> round(trn_sum_from_iss)) as iss_not_integer,
    count(*) filter (where purchase_sum <> round(purchase_sum)) as ps_not_integer,
    count(*) filter (where product_quantity = 0) as qty_0,
    count(*) filter (where product_quantity = 0 and trn_sum_from_iss > 0) as qty_0_sum_positive,
    count(*) filter (where product_quantity <> round(product_quantity)) as qty_fraction,
    count(*) filter (where trn_sum_from_iss = 0) as iss_0,
    count(*) filter (where purchase_sum = 0) as ps_0
from purchases;

-- name: age_bins
select
    case
        when age < 0 then '< 0'
        when age < getvariable('age_min') then '0 - ' || (getvariable('age_min') - 1)
        when age <= getvariable('age_max') then getvariable('age_min') || ' - ' || getvariable('age_max')
        else '> ' || getvariable('age_max')
    end as age_bin,
    count(*) as n_clients,
    count(*) filter (where client_id in (select client_id from uplift_train)) as n_train
from clients
group by 1
order by min(age);

-- name: age_hist
select age, count(*) as n_clients from clients where age between 0 and 130 group by 1 order by 1;

-- name: age_spikes
select age, count(*) as n_clients from clients where age > getvariable('age_max') group by 1 order by 2 desc limit 5;

-- name: gender
select gender, count(*) as n_clients, count(*) / sum(count(*)) over () as share from clients group by 1 order by 1;

-- name: client_dates
with h as (select max(transaction_datetime) as last_dt from purchases)
select
    count(*) as n_clients,
    count(*) filter (where first_redeem_date is null) as redeem_null,
    count(*) filter (where first_redeem_date < first_issue_date) as redeem_before_issue,
    count(*) filter (where first_issue_date > (select last_dt from h)) as issue_after_history,
    count(*) filter (where first_redeem_date::date > getvariable('cutoff')) as redeem_after_cutoff,
    min(first_issue_date) as min_issue,
    max(first_issue_date) as max_issue,
    max(first_redeem_date) as max_redeem
from clients;

-- name: redeem_after_cutoff_by_month
select date_trunc('month', first_redeem_date)::date as month, count(*) as n_clients
from clients
where first_redeem_date::date > getvariable('cutoff')
group by 1
order by 1;

-- name: clients_time_offset
-- Даты clients против первых событий в purchases. Беру только клиентов, у которых дата из clients
-- попадает в окно истории: раньше начала истории первой покупки или списания не видно.
with h as (
    select min(transaction_datetime) as first_dt, max(transaction_datetime) as last_dt from purchases
),
trn as (
    select
        client_id,
        transaction_id,
        any_value(transaction_datetime) as dt,
        any_value(regular_points_spent) as reg_spent
    from purchases
    group by all
),
firsts as (
    select client_id, min(dt) as first_trn, min(dt) filter (where reg_spent < 0) as first_reg_spend
    from trn
    group by client_id
),
lags as (
    select 'first_issue_date - первая покупка' as what, first_issue_date - first_trn as lag
    from clients join firsts using (client_id)
    where first_issue_date between (select first_dt from h) and (select last_dt from h)
    union all
    select 'first_redeem_date - первое списание обычных баллов', first_redeem_date - first_reg_spend
    from clients join firsts using (client_id)
    where first_redeem_date between (select first_dt from h) and (select last_dt from h)
)
select
    what,
    count(*) as n_clients,
    count(*) filter (where lag = interval 3 hour) as exactly_3h,
    count(*) filter (where lag > interval 2 hour and lag < interval 3 hour) as from_2h_to_3h,
    count(*) filter (where lag < interval 0 hour) as negative,
    count(*) filter (where lag is null) as no_event,
    count(*) filter (where lag > interval 3 hour) as more_than_3h
from lags
group by what
order by what;

-- name: spent_before_redeem
-- Есть ли списания баллов раньше first_redeem_date: по исходным датам и после сдвига clients на -3 часа.
with h as (
    select min(transaction_datetime) as first_dt, max(transaction_datetime) as last_dt from purchases
),
trn as (
    select
        client_id,
        transaction_id,
        any_value(transaction_datetime) as dt,
        any_value(regular_points_spent) + any_value(express_points_spent) as points_spent
    from purchases
    group by all
),
first_spend as (
    select client_id, min(dt) as first_spend_dt from trn where points_spent < 0 group by client_id
)
select
    count(*) as n_clients,
    count(*) filter (where first_spend_dt < first_redeem_date) as spend_before_redeem_raw,
    count(*) filter (where first_spend_dt < first_redeem_date - interval 3 hour) as spend_before_redeem_shifted
from clients
left join first_spend using (client_id)
where first_redeem_date between (select first_dt from h) and (select last_dt from h);

-- name: daily
with trn as (
    select client_id, transaction_id, any_value(transaction_datetime)::date as day
    from purchases
    group by all
)
select day, count(*) as n_transactions, count(distinct client_id) as n_clients
from trn
group by day
order by day;

-- name: train_history
-- История покупок клиентов из uplift_train: число чеков, первый и последний чек.
with trn as (
    select client_id, transaction_id, any_value(transaction_datetime) as dt
    from purchases
    group by all
),
per_client as (
    select client_id, count(*) as n_trn, min(dt) as first_dt, max(dt) as last_dt
    from trn
    where client_id in (select client_id from uplift_train)
    group by client_id
),
h as (select max(dt) as last_dt from trn)
select
    count(*) as n_clients,
    quantile_cont(n_trn, [0.05, 0.25, 0.5, 0.75, 0.95]) as n_trn_q,
    count(*) filter (where n_trn = 1) as one_transaction,
    count(*) filter (where last_dt::date = (select last_dt::date from h)) as last_purchase_on_last_day,
    count(*) filter (where last_dt < (select last_dt from h) - interval 30 day) as no_purchases_last_30d,
    max(date_diff('day', last_dt, (select last_dt from h))) as max_days_since_last
from per_client;
