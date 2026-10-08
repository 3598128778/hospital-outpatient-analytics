WITH visit_by_registration AS (
 SELECT registration_id, SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS visits
 FROM visits GROUP BY registration_id
), charge_by_registration AS (
 SELECT registration_id,
 SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE 0 END) AS gross_cents,
 SUM(CASE WHEN kind = 'refund' THEN amount_cents ELSE 0 END) AS refund_cents
 FROM charges GROUP BY registration_id
)
SELECT r.business_date, r.department, r.period,
 SUM(CASE WHEN r.status = 'valid' THEN 1 ELSE 0 END) AS registrations,
 SUM(COALESCE(v.visits, 0)) AS visits,
 SUM(COALESCE(c.gross_cents, 0)) AS gross_cents,
 SUM(COALESCE(c.refund_cents, 0)) AS refund_cents,
 SUM(COALESCE(c.gross_cents, 0) - COALESCE(c.refund_cents, 0)) AS net_cents
FROM registrations r
LEFT JOIN visit_by_registration v ON r.registration_id = v.registration_id
LEFT JOIN charge_by_registration c ON r.registration_id = c.registration_id
GROUP BY r.business_date, r.department, r.period
ORDER BY r.business_date, r.department, r.period;
