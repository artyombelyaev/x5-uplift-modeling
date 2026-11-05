-- Этап 6: витрина итоговых скоров, одна строка на клиента clients.
-- uplift_score - финальная модель (трансформация классов, seed 42), p_t - модель отклика.
-- Перцентиль и дециль считаются отдельно для клиентов эксперимента и вне его. Флаг send - только вне эксперимента:
-- первые k клиентов по uplift_score, где k - доля, выбранная на valid для ближайшего к getvariable('r') значения
-- сетки r (data/send_shares.parquet).

-- name: scores
with base as (
    select
        c.client_id,
        u.client_id is not null as in_experiment,
        s.part,
        r.uplift_score,
        r.p_t
    from clients c
    join read_parquet(getvariable('scores_parquet')) r using (client_id)
    left join uplift_train u using (client_id)
    left join read_parquet(getvariable('split_parquet')) s using (client_id)
),
ranked as (
    select
        *,
        -- 0 - самый высокий скор; при равных скорах порядок по client_id, чтобы витрина была детерминированной
        percent_rank() over w as uplift_pct_rank,
        ntile(10) over w as uplift_decile,
        ntile(10) over (partition by in_experiment order by p_t desc, client_id) as p_t_decile,
        row_number() over w as uplift_rank,
        count(*) over (partition by in_experiment) as group_size
    from base
    window w as (partition by in_experiment order by uplift_score desc, client_id)
)
select
    client_id,
    in_experiment,
    part,
    uplift_score,
    p_t,
    uplift_pct_rank,
    uplift_decile,
    p_t_decile,
    case
        when in_experiment then null
        else uplift_rank <= group_size * (
            select k from read_parquet(getvariable('send_shares_parquet')) order by abs(r - getvariable('r')), r limit 1
        )
    end as send
from ranked
order by client_id;

-- name: mart_checks
select
    count(*) as n_rows,
    count(distinct client_id) as n_clients,
    (select count(*) from clients) as n_clients_table,
    count(*) filter (where in_experiment) as n_experiment,
    count(*) filter (where not in_experiment) as n_outside,
    count(*) filter (where part = 'train') as n_train,
    count(*) filter (where part = 'valid') as n_valid,
    count(*) filter (where part = 'test') as n_test,
    count(*) filter (where uplift_score is null or p_t is null) as n_null_scores,
    count(distinct uplift_score) as n_distinct_uplift_scores
from scores;

-- name: decile_sizes
select in_experiment, uplift_decile, count(*) as n_clients, min(uplift_score) as min_score, max(uplift_score) as max_score
from scores
group by all
order by in_experiment, uplift_decile;

-- name: decile_summary
-- Клиенты вне эксперимента по децилям uplift_score: размер, скоры и медианы ключевых признаков.
select
    s.uplift_decile,
    count(*) as n_clients,
    avg(s.uplift_score) as avg_uplift_score,
    avg(s.p_t) as avg_p_t,
    median(f.days_since_last) as days_since_last,
    median(f.n_trn_all) as n_trn_all,
    median(f.sum_all) as sum_all,
    median(f.card_age_days) as card_age_days,
    avg(f.share_spend_all) as share_spend_all,
    median(f.age) as age
from scores s
join read_parquet(getvariable('features_all_parquet')) f using (client_id)
where not s.in_experiment
group by s.uplift_decile
order by s.uplift_decile;

-- name: send_summary
-- Сколько клиентов вне эксперимента получат сообщение при текущем r.
select
    getvariable('r') as r,
    (select k from read_parquet(getvariable('send_shares_parquet')) order by abs(r - getvariable('r')), r limit 1) as k_from_valid,
    count(*) filter (where send) as n_send,
    count(*) as n_outside,
    avg(send::int) as share_send
from scores
where not in_experiment;

-- name: send_list
-- Список на рассылку при текущем r: клиенты вне эксперимента с send, по убыванию uplift_score.
select client_id, uplift_score, uplift_decile, p_t
from scores
where send
order by uplift_score desc, client_id;

-- name: top_overlap
-- Пересечение топ-10% и топ-30% по модели отклика и по uplift-модели среди клиентов вне эксперимента.
with o as (
    select
        uplift_decile <= 1 as up10, p_t_decile <= 1 as pt10,
        uplift_decile <= 3 as up30, p_t_decile <= 3 as pt30
    from scores
    where not in_experiment
)
select
    count(*) filter (where up10 and pt10) / count(*) filter (where up10) as overlap_top10,
    count(*) filter (where up30 and pt30) / count(*) filter (where up30) as overlap_top30
from o;

-- name: tied_scores
-- Доля клиентов, у которых uplift_score совпадает хотя бы с одним другим клиентом той же группы.
with c as (
    select in_experiment, count(*) over (partition by in_experiment, uplift_score) as n_same
    from scores
)
select in_experiment, count(*) as n_clients, avg((n_same > 1)::int) as share_tied
from c
group by 1
order by 1 desc;

-- name: decile_transfer
-- Границы децилей uplift_score, посчитанные в эксперименте, и доля клиентов вне эксперимента выше каждой границы.
-- Если распределения скоров совпадают, выше нижней границы дециля d должно быть около d x 10% клиентов.
with bounds as (
    select uplift_decile, min(uplift_score) as lower_bound
    from scores
    where in_experiment
    group by 1
)
select
    b.uplift_decile,
    b.lower_bound,
    b.uplift_decile / 10 as expected_share,
    avg((s.uplift_score >= b.lower_bound)::int) as share_outside_above
from bounds b
cross join (select uplift_score from scores where not in_experiment) s
group by all
order by 1;
