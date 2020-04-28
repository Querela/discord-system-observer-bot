import typing


def make_table(
    rows: typing.List,
    headers: typing.Optional[typing.Set[str]],
    alignments: typing.Optional[typing.Set[str]] = None,
    wrap_markdown: bool = True,
    header_separator: bool = True,
    column_separators: bool = True,
) -> typing.Optional[str]:
    # get number of columns
    if headers:
        num_columns = len(headers)
    elif rows:
        num_columns = len(rows[0])
    else:
        # no headers and no rows, can't output anything
        return None

    # check input correct!
    if rows:
        assert len({len(row) for row in rows}) == 1, (
            "All data rows should have the same number of columns! "
            f"Got {set(len(row) for row in rows)}"
        )
    if headers and rows:
        assert len(headers) == len(rows[0]), (
            "Number of headers and number of columns in data rows "
            "should be the same! "
            f"headers: {len(headers)}, rows[0]: {len(rows[0])}"
        )
    if alignments:
        assert len(alignments) == num_columns, (
            "Number of alignments should match number of data "
            "columns/headers! "
            f"alignments: {len(alignments)}, #columns: {num_columns}"
        )

    # compute width of columns
    column_widths = [
        max(
            len(str(row[field_idx]))
            for row in [headers or [""] * num_columns] + (rows or [])
        )
        for field_idx in range(num_columns)
    ]

    col_sep_str = " | " if column_separators else " "

    table_strs = list()

    # header + separator
    if headers:
        table_strs.append(
            # col_sep_str.lstrip() +
            col_sep_str.join(
                [
                    f"{header:{column_width}s}"
                    for header, column_width in zip(headers, column_widths)
                ]
            )
            # + col_sep_str.rstrip()
        )

        # separator
        if header_separator:
            table_strs.append(
                # col_sep_str.lstrip() +
                col_sep_str.join(["-" * column_width for column_width in column_widths])
                # + col_sep_str.rstrip()
            )

    # data rows
    if rows:

        def _get_type_align(field):
            if isinstance(field, (int, float)):
                return "numeric", ">"
            if isinstance(field, (bool)):
                return "bool", ">"
            if field is None:
                return "None", ">"
            return "str", "<"

        # check alignments else guess from first line
        check_each = False
        if not alignments:
            # alignments = ()
            # col_types = ()
            check_each = True

            # for field_idx, field in enumerate(rows[0]):
            #     col_type, alignment = _get_type_align(field)
            #     col_types += col_type
            #     alignments += alignment

        rows_str = list()
        for row in rows:
            cells = list()
            for field_idx, (field, column_width) in enumerate(zip(row, column_widths)):
                # if alignments provided, just dump
                if not check_each:
                    if field is None or isinstance(field, bool):
                        field = str(field)
                    cells.append(f"{field:{alignments[field_idx]}{column_width}}")
                else:
                    _, alignment = _get_type_align(field)
                    # if col_type != col_types[field_idx]:
                    if field is None or isinstance(field, bool):
                        field = str(field)
                    cells.append(f"{field:{alignment}{column_width}}")

            rows_str.append(
                # col_sep_str.lstrip() +
                col_sep_str.join(cells)
                # + col_sep_str.rstrip()
            )

        table_strs.extend(rows_str)

    table_str = "\n".join(table_strs)

    if wrap_markdown:
        table_str = "\n".join(["```", table_str, "```"])

    return table_str


def dump_dict_kv(
    dict_kv: typing.Dict[str, typing.Any], wrap_markdown: bool = True
) -> typing.Optional[str]:
    if not dict_kv:
        return None

    len_keys = max(len(k) for k in dict_kv.keys())
    len_vals = max(
        len(str(v)) for v in dict_kv.values() if isinstance(v, (int, float, bool))
    )

    text = "\n".join([f"{k:<{len_keys}} {v:>{len_vals}}" for k, v in dict_kv.items()])

    # return text

    text = make_table(
        list(dict_kv.items()),
        None,
        alignments=("<", ">"),
        wrap_markdown=wrap_markdown,
        header_separator=False,
        column_separators=False,
    )

    return text
