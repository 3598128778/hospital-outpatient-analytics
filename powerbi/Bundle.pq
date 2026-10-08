// Create a blank Power Query named Bundle. Update this ONE directory.
let
    Root = "C:\hospital-outpatient-analytics\artifacts\",
    ReadCSV = (name as text) as table => Table.PromoteHeaders(
        Csv.Document(File.Contents(Root & name), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
        [PromoteAllScalars=true]),
    Daily = Table.TransformColumnTypes(ReadCSV("daily_metrics.csv"), {
        {"business_date", type date}, {"department", type text}, {"period", type text},
        {"registrations", Int64.Type}, {"visits", Int64.Type}, {"gross_cents", Int64.Type},
        {"refund_cents", Int64.Type}, {"net_cents", Int64.Type}}, "en-US"),
    Alerts = Table.TransformColumnTypes(ReadCSV("anomalies.csv"), {
        {"business_date", type date}, {"actual", type number}, {"baseline", type number},
        {"threshold", type number}, {"deviation_pct", type number}, {"baseline_samples", Int64.Type}}, "en-US"),
    Registrations = Table.TransformColumnTypes(ReadCSV("registration_details.csv"), {{"business_date", type date}}, "en-US"),
    Visits = ReadCSV("visit_details.csv"),
    Charges = Table.TransformColumnTypes(ReadCSV("charge_details.csv"), {{"amount_cents", Int64.Type}}, "en-US"),
    Summary = #table(type table [summary=text], {{Text.FromBinary(File.Contents(Root & "summary.md"), TextEncoding.Utf8)}})
in
    [Daily=Daily, Alerts=Alerts, Registrations=Registrations, Visits=Visits, Charges=Charges, Summary=Summary]
