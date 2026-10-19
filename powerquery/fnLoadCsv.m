// ALL DATA IS SYNTHETIC (invented offices, people and figures). Phase 3 Power Query (M).
// Syntax-reviewed on macOS only: NOT executed in Power Query / Power BI yet.
// Query name: fnLoadCsv   (function; disable "Enable load" for this query)
// Reads one CSV from DataFolder, promotes headers and turns empty strings into null
// (needed for the nullable fact_projects[CompletionDate]). Types are applied by each table query.
(fileName as text) as table =>
let
    Folder   = Text.TrimEnd(Text.TrimEnd(DataFolder, "/"), "\"),
    Sep      = if Text.Contains(Folder, "\") then "\" else "/",
    FilePath = Folder & Sep & fileName,
    Raw      = Csv.Document(File.Contents(FilePath), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Raw, [PromoteAllScalars = true]),
    BlankToNull = Table.TransformColumns(
        Promoted,
        List.Transform(
            Table.ColumnNames(Promoted),
            (col) => {col, (v) => if v = "" then null else v, type nullable text}
        )
    )
in
    BlankToNull
