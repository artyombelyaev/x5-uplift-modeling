-- Этап 3: витрина признаков, одна строка на клиента эксперимента.
-- Источники: purchases до CUTOFF включительно и clients (даты сдвинуты в staging.sql). Target и treatment
-- не используются. Окна - последние 7, 14 и 30 дней до CUTOFF включительно и вся история.

-- name: features
with trn as (
    -- одна строка на чек; purchase_sum и баллы берутся один раз на чек
    select
        client_id,
        transaction_id,
        any_value(transaction_datetime)::date as day,
        any_value(store_id) as store_id,
        any_value(purchase_sum) as purchase_sum,
        any_value(regular_points_received) as reg_received,
        any_value(express_points_received) as exp_received,
        -any_value(regular_points_spent) as reg_spent,
        -any_value(express_points_spent) as exp_spent
    from purchases
    where transaction_datetime::date <= getvariable('cutoff')
        and client_id in (select client_id from uplift_train)
    group by client_id, transaction_id
),
trn_flags as (
    select
        *,
        day > getvariable('cutoff') - 7 as in_7d,
        day > getvariable('cutoff') - 14 as in_14d,
        day > getvariable('cutoff') - 30 as in_30d,
        day > getvariable('cutoff') - 28 and day <= getvariable('cutoff') - 14 as in_prev_14d,
        reg_spent + exp_spent > 0 as has_spend
    from trn
),
trn_agg as (
    select
        client_id,

        count(*) filter (where in_7d) as n_trn_7d,
        count(*) filter (where in_14d) as n_trn_14d,
        count(*) filter (where in_30d) as n_trn_30d,
        count(*) as n_trn_all,

        coalesce(sum(purchase_sum) filter (where in_7d), 0) as sum_7d,
        coalesce(sum(purchase_sum) filter (where in_14d), 0) as sum_14d,
        coalesce(sum(purchase_sum) filter (where in_30d), 0) as sum_30d,
        sum(purchase_sum) as sum_all,

        avg(purchase_sum) filter (where in_7d) as avg_check_7d,
        avg(purchase_sum) filter (where in_14d) as avg_check_14d,
        avg(purchase_sum) filter (where in_30d) as avg_check_30d,
        avg(purchase_sum) as avg_check_all,

        coalesce(sum(reg_received) filter (where in_7d), 0) as reg_received_7d,
        coalesce(sum(reg_received) filter (where in_14d), 0) as reg_received_14d,
        coalesce(sum(reg_received) filter (where in_30d), 0) as reg_received_30d,
        sum(reg_received) as reg_received_all,

        -- экспресс-баллы начисляются редкими акциями, последняя - 2019-03-10: в окнах 7-30 дней почти всегда 0
        sum(exp_received) as exp_received_all,

        coalesce(sum(reg_spent) filter (where in_7d), 0) as reg_spent_7d,
        coalesce(sum(reg_spent) filter (where in_14d), 0) as reg_spent_14d,
        coalesce(sum(reg_spent) filter (where in_30d), 0) as reg_spent_30d,
        sum(reg_spent) as reg_spent_all,

        coalesce(sum(exp_spent) filter (where in_7d), 0) as exp_spent_7d,
        coalesce(sum(exp_spent) filter (where in_14d), 0) as exp_spent_14d,
        coalesce(sum(exp_spent) filter (where in_30d), 0) as exp_spent_30d,
        sum(exp_spent) as exp_spent_all,

        avg(has_spend::int) filter (where in_7d) as share_spend_7d,
        avg(has_spend::int) filter (where in_14d) as share_spend_14d,
        avg(has_spend::int) filter (where in_30d) as share_spend_30d,
        avg(has_spend::int) as share_spend_all,

        count(distinct store_id) filter (where in_7d) as n_stores_7d,
        count(distinct store_id) filter (where in_14d) as n_stores_14d,
        count(distinct store_id) filter (where in_30d) as n_stores_30d,
        count(distinct store_id) as n_stores_all,

        date_diff('day', max(day), getvariable('cutoff')) as days_since_last,
        date_diff('day', min(day), getvariable('cutoff')) as days_since_first,

        -- тренд: последние 14 дней против 14 дней перед ними, (a - b) / (a + b) от -1 до 1
        (count(*) filter (where in_14d) - count(*) filter (where in_prev_14d))
            / nullif(count(*) filter (where in_14d) + count(*) filter (where in_prev_14d), 0) as trend_trn_14d,
        (coalesce(sum(purchase_sum) filter (where in_14d), 0) - coalesce(sum(purchase_sum) filter (where in_prev_14d), 0))
            / nullif(coalesce(sum(purchase_sum) filter (where in_14d), 0)
                     + coalesce(sum(purchase_sum) filter (where in_prev_14d), 0), 0) as trend_sum_14d
    from trn_flags
    group by client_id
),
products as (
    -- разнообразие товаров считается по строкам чеков
    select
        client_id,
        count(distinct product_id) filter (where day > getvariable('cutoff') - 7) as n_products_7d,
        count(distinct product_id) filter (where day > getvariable('cutoff') - 14) as n_products_14d,
        count(distinct product_id) filter (where day > getvariable('cutoff') - 30) as n_products_30d,
        count(distinct product_id) as n_products_all
    from (
        select client_id, product_id, transaction_datetime::date as day
        from purchases
        where transaction_datetime::date <= getvariable('cutoff')
            and client_id in (select client_id from uplift_train)
    )
    group by client_id
),
client_features as (
    select
        client_id,
        case when age between getvariable('age_min') and getvariable('age_max') then age end as age,
        gender,
        date_diff('day', first_issue_date::date, getvariable('cutoff')) as card_age_days,
        coalesce(first_redeem_date::date <= getvariable('cutoff'), false)::int as redeemed_before_cutoff,
        case
            when first_redeem_date::date <= getvariable('cutoff')
            then date_diff('day', first_issue_date::date, first_redeem_date::date)
        end as days_issue_to_redeem
    from clients
)
select
    u.client_id,
    c.* exclude (client_id),
    t.* exclude (client_id),
    p.* exclude (client_id)
from uplift_train u
left join client_features c using (client_id)
left join trn_agg t using (client_id)
left join products p using (client_id)
order by u.client_id;

-- name: mart_checks
select
    count(*) as n_rows,
    count(distinct client_id) as n_clients,
    (select count(*) from uplift_train) as n_experiment,
    count(*) filter (where client_id not in (select client_id from uplift_train)) as not_in_experiment,
    (select count(*) from (describe select * from read_parquet(getvariable('features_parquet')))) as n_columns
from read_parquet(getvariable('features_parquet'));

-- name: mart_profile
-- Доля NULL, минимум, медиана и максимум каждой колонки витрины. unpivot выбрасывает NULL,
-- поэтому долю NULL считаю как 1 - непустые / все строки.
with x as (
    unpivot (
        select columns(* exclude (client_id, gender))::double
        from read_parquet(getvariable('features_parquet'))
    )
    on columns(*) into name feature value v
)
select
    feature,
    1 - count(*) / (select count(*) from read_parquet(getvariable('features_parquet'))) as null_share,
    min(v) as min,
    median(v) as median,
    max(v) as max
from x
group by feature;

-- name: mart_gender
select gender, count(*) as n_clients from read_parquet(getvariable('features_parquet')) group by 1 order by 1;

-- name: mart_moments
-- Среднее и дисперсия каждого признака по группам: проверка, что признаки до коммуникации сбалансированы.
-- Treatment здесь только для проверки, в витрину он не входит.
with x as (
    unpivot (
        select u.treatment_flg, columns(f.* exclude (client_id, gender))::double
        from read_parquet(getvariable('features_parquet')) f
        join uplift_train u using (client_id)
    )
    on columns(* exclude (treatment_flg)) into name feature value v
)
select
    feature,
    avg(v) filter (where treatment_flg = 1) as mean_treatment,
    avg(v) filter (where treatment_flg = 0) as mean_control,
    var_samp(v) filter (where treatment_flg = 1) as var_treatment,
    var_samp(v) filter (where treatment_flg = 0) as var_control
from x
group by feature;
