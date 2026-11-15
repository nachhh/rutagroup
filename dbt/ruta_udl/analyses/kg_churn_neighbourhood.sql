-- KG demo: "Which active customers share carriers with churned customers, and how much?"
-- Path:  (churned:Customer)-[books]->(:Shipment)<-[carries]-(k:Carrier)-[carries]->(:Shipment)<-[books]-(c:Customer)
-- On tables this is a chain of self-joins on kg_edges. The same question in GQL (ISO graph query language, supported
-- by Spanner Graph / BigQuery graph queries over a CREATE PROPERTY GRAPH definition):
--   GRAPH ruta
--   MATCH (ch:Customer {is_churned: true})-[:books]->(:Shipment)<-[:carries]-(k:Carrier)
--         -[:carries]->(:Shipment)<-[:books]-(c:Customer {is_churned: false})
--   RETURN k.label, COUNT(DISTINCT ch) AS churned, COUNT(DISTINCT c) AS exposed
-- Compile with `dbt compile -s kg_churn_neighbourhood`, run the SQL in target/compiled/.
with nodes as (select * from {{ ref('kg_nodes') }}),
edges as (select * from {{ ref('kg_edges') }}),

churned as (
    select node_id from nodes
    where node_type = 'Customer' and coalesce(lax_bool(properties.is_churned), false)  -- JSON null (no subscription) → LAX_BOOL gives NULL instead of failing like BOOL()
),

carrier_customer as (   -- project the graph onto Carrier ↔ Customer (2 hops each way through Shipment)
    select distinct c.src_id as carrier_id, b.src_id as customer_id
    from edges b
    join edges c on c.predicate = 'carries' and c.dst_id = b.dst_id
    where b.predicate = 'books'
)

select
    n.label                                                     as carrier,
    count(distinct if(ch.node_id is not null, cc.customer_id, null)) as churned_customers,
    count(distinct if(ch.node_id is null, cc.customer_id, null))     as active_customers_exposed,
    round(safe_divide(count(distinct if(ch.node_id is not null, cc.customer_id, null)),
                      count(distinct cc.customer_id)), 3)       as churn_share
from carrier_customer cc
join nodes n on n.node_id = cc.carrier_id
left join churned ch on ch.node_id = cc.customer_id
group by 1
order by churn_share desc
limit 10
