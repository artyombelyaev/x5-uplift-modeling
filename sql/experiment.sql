-- Этап 2: проверка эксперимента. Агрегаты по группам, статистика - в src/stats.py.
-- Чек - пара (client_id, transaction_id), агрегаты по чекам - через CTE «одна строка на чек».

-- name: group_sizes
-- Размеры групп на всех клиентах и в каждой части разбиения.
with s as (
    select t.treatment_flg, p.part
    from uplift_train t
    join read_parquet(getvariable('split_parquet')) p using (client_id)
)
select 'all' as part, count(*) filter (where treatment_flg = 1) as n_treatment, count(*) filter (where treatment_flg = 0) as n_control
from s
union all
select part, count(*) filter (where treatment_flg = 1), count(*) filter (where treatment_flg = 0)
from s
group by part;

-- name: covariates
-- Ковариаты для баланса: одна строка на клиента эксперимента. Только данные до CUTOFF включительно.
with trn as (
    select
        client_id,
        transaction_id,
        any_value(transaction_datetime) as dt,
        any_value(purchase_sum) as purchase_sum
    from purchases
    where transaction_datetime::date <= getvariable('cutoff')
    group by all
),
hist as (
    select client_id, count(*) as n_transactions, sum(purchase_sum) as purchase_sum, max(dt) as last_dt
    from trn
    group by client_id
)
select
    t.client_id,
    t.treatment_flg,
    case when c.age between getvariable('age_min') and getvariable('age_max') then c.age end as age,
    (c.age not between getvariable('age_min') and getvariable('age_max'))::int as age_null,
    (c.gender = 'F')::int as gender_f,
    (c.gender = 'M')::int as gender_m,
    (c.gender = 'U')::int as gender_u,
    date_diff('day', c.first_issue_date::date, getvariable('cutoff')) as card_age_days,
    coalesce(c.first_redeem_date::date <= getvariable('cutoff'), false)::int as redeemed_before_cutoff,
    coalesce(h.n_transactions, 0) as n_transactions,
    coalesce(h.purchase_sum, 0) as purchase_sum,
    date_diff('day', h.last_dt::date, getvariable('cutoff')) as days_since_last
from uplift_train t
join clients c using (client_id)
left join hist h using (client_id);

-- name: covariate_moments
-- Среднее и дисперсия каждой ковариаты по группам: из них SMD. Нужна вьюха covariates (db.create_view).
with x as (
    unpivot (
        select treatment_flg, columns(* exclude (client_id, treatment_flg))::double
        from covariates
    )
    on columns(* exclude (treatment_flg)) into name covariate value v
)
select
    covariate,
    avg(v) filter (where treatment_flg = 1) as mean_treatment,
    avg(v) filter (where treatment_flg = 0) as mean_control,
    var_samp(v) filter (where treatment_flg = 1) as var_treatment,
    var_samp(v) filter (where treatment_flg = 0) as var_control,
    count(v) filter (where treatment_flg = 1) as n_treatment,
    count(v) filter (where treatment_flg = 0) as n_control
from x
group by covariate;

-- name: daily_by_group
-- Последние 21 день истории до CUTOFF: по каждому дню и группе - доля купивших клиентов, среднее число чеков
-- на клиента и его дисперсия. Среднее и дисперсия - по всем клиентам группы, включая тех, у кого чеков 0.
with days as (
    select unnest(generate_series(getvariable('cutoff') - interval 20 day, getvariable('cutoff')::timestamp, interval 1 day))::date as day
),
trn as (
    select client_id, transaction_id, any_value(transaction_datetime)::date as day
    from purchases
    where transaction_datetime::date between getvariable('cutoff') - interval 20 day and getvariable('cutoff')
    group by all
),
per_client_day as (
    select client_id, day, count(*) as n_trn
    from trn
    group by all
),
groups as (
    select treatment_flg, count(*) as n_clients from uplift_train group by 1
),
agg as (
    select u.treatment_flg, p.day, count(*) as n_buyers, sum(p.n_trn) as s1, sum(p.n_trn * p.n_trn) as s2
    from per_client_day p
    join uplift_train u using (client_id)
    group by all
)
select
    d.day,
    g.treatment_flg,
    g.n_clients,
    coalesce(a.n_buyers, 0) as n_buyers,
    coalesce(a.s1, 0) / g.n_clients as trn_per_client,
    (coalesce(a.s2, 0) - coalesce(a.s1, 0) ^ 2 / g.n_clients) / (g.n_clients - 1) as trn_var
from days d
cross join groups g
left join agg a on a.day = d.day and a.treatment_flg = g.treatment_flg
order by d.day, g.treatment_flg;

-- name: redeem_after_cutoff
-- Доля клиентов с first_redeem_date после CUTOFF по группам. Это событие после коммуникации: проверка, а не признак.
select
    treatment_flg,
    count(*) as n_clients,
    count(*) filter (where c.first_redeem_date::date > getvariable('cutoff')) as n_redeem_after
from uplift_train t
join clients c using (client_id)
group by 1
order by 1;

-- name: target_by_group
select treatment_flg, count(*) as n_clients, sum(target) as n_buyers
from uplift_train
group by 1
order by 1;

-- name: target_arrays
select treatment_flg, target from uplift_train;

-- name: recent_buyers
-- Проверка на уровне клиента: покупал ли клиент в последние 3 и 7 дней истории до CUTOFF.
with recent as (
    select
        client_id,
        max(transaction_datetime)::date > getvariable('cutoff') - interval 3 day as bought_3d,
        max(transaction_datetime)::date > getvariable('cutoff') - interval 7 day as bought_7d
    from purchases
    where transaction_datetime::date <= getvariable('cutoff')
    group by client_id
)
select
    t.treatment_flg,
    count(*) as n_clients,
    count(*) filter (where r.bought_3d) as n_bought_3d,
    count(*) filter (where r.bought_7d) as n_bought_7d
from uplift_train t
left join recent r using (client_id)
group by 1
order by 1;
