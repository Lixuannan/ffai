from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ffai.errors import CommandBuildError
from ffai.models import PandocTask
from ffai.pandoc_builder import build_command, describe_allowed_extra_options


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "notes.md"
    path.write_text("# Heading\n\nHello.\n", encoding="utf-8")
    return path


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "out.docx"


def task_for(source: Path, output: Path, **fields: object) -> PandocTask:
    return PandocTask(inputs=[str(source)], output=str(output), **fields)


def test_minimal_command_puts_output_before_inputs(
    source: Path, output: Path
) -> None:
    command = build_command(task_for(source, output))

    assert command == ["pandoc", "-o", str(output.resolve()), str(source.resolve())]


def test_minimal_command_omits_formats(source: Path, output: Path) -> None:
    command = build_command(task_for(source, output))

    assert "-f" not in command
    assert "-t" not in command


def test_full_option_set_order(tmp_path: Path, source: Path, output: Path) -> None:
    template = tmp_path / "template.tex"
    template.write_text("$body$", encoding="utf-8")
    reference_doc = tmp_path / "reference.docx"
    reference_doc.write_bytes(b"placeholder")
    bibliography = tmp_path / "refs.bib"
    bibliography.write_text("@book{x, title={X}}", encoding="utf-8")
    csl = tmp_path / "style.csl"
    csl.write_text("<style/>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()

    task = task_for(
        source,
        output,
        from_format="markdown",
        to_format="docx",
        standalone=True,
        toc=True,
        toc_depth=3,
        number_sections=True,
        shift_heading_level_by=2,
        metadata=["title=My Doc", "author=Jane Doe"],
        template=str(template),
        reference_doc=str(reference_doc),
        pdf_engine="xelatex",
        highlight_style="tango",
        embed_resources=True,
        citeproc=True,
        bibliography=[str(bibliography)],
        csl=str(csl),
        resource_path=[str(assets)],
        extra_options=["--columns", "80", "--top-level-division", "chapter"],
    )

    command = build_command(task)

    assert command == [
        "pandoc",
        "-f",
        "markdown",
        "-t",
        "docx",
        "--standalone",
        "--toc",
        "--toc-depth",
        "3",
        "--number-sections",
        "--shift-heading-level-by",
        "2",
        "-M",
        "title=My Doc",
        "-M",
        "author=Jane Doe",
        "--template",
        str(template.resolve()),
        "--reference-doc",
        str(reference_doc.resolve()),
        "--pdf-engine",
        "xelatex",
        "--highlight-style",
        "tango",
        "--embed-resources",
        "--citeproc",
        "--bibliography",
        str(bibliography.resolve()),
        "--csl",
        str(csl.resolve()),
        "--resource-path",
        str(assets.resolve()),
        "--columns",
        "80",
        "--top-level-division",
        "chapter",
        "-o",
        str(output.resolve()),
        str(source.resolve()),
    ]


def test_multiple_metadata_entries_repeat_the_flag(
    source: Path, output: Path
) -> None:
    command = build_command(
        task_for(source, output, metadata=["title=One", "subtitle=Two"])
    )

    assert command[1:5] == ["-M", "title=One", "-M", "subtitle=Two"]


def test_paths_with_spaces_stay_single_argv_entries(tmp_path: Path) -> None:
    spaced_source = tmp_path / "my notes.md"
    spaced_source.write_text("# Spaced\n", encoding="utf-8")
    spaced_output = tmp_path / "out put.docx"
    spaced_template = tmp_path / "my template.tex"
    spaced_template.write_text("$body$", encoding="utf-8")
    spaced_assets = tmp_path / "my assets"
    spaced_assets.mkdir()

    command = build_command(
        PandocTask(
            inputs=[str(spaced_source)],
            output=str(spaced_output),
            template=str(spaced_template),
            resource_path=[str(spaced_assets)],
        )
    )

    assert str(spaced_source.resolve()) in command
    assert str(spaced_output.resolve()) in command
    assert str(spaced_template.resolve()) in command
    assert str(spaced_assets.resolve()) in command
    assert command[-3:] == [
        "-o",
        str(spaced_output.resolve()),
        str(spaced_source.resolve()),
    ]


def test_missing_inputs_rejected(output: Path) -> None:
    with pytest.raises(CommandBuildError, match="No input files"):
        build_command(PandocTask(inputs=[], output=str(output)))


def test_nonexistent_input_rejected(tmp_path: Path, output: Path) -> None:
    with pytest.raises(CommandBuildError, match="Input file does not exist"):
        build_command(PandocTask(inputs=[str(tmp_path / "nope.md")], output=str(output)))


def test_input_directory_rejected(tmp_path: Path, output: Path) -> None:
    with pytest.raises(CommandBuildError, match="Input is not a regular file"):
        build_command(PandocTask(inputs=[str(tmp_path)], output=str(output)))


def test_missing_output_rejected(source: Path) -> None:
    with pytest.raises(CommandBuildError, match="No output file"):
        build_command(PandocTask(inputs=[str(source)], output=None))


def test_output_directory_missing_rejected(tmp_path: Path, source: Path) -> None:
    with pytest.raises(CommandBuildError, match="Output directory does not exist"):
        build_command(
            PandocTask(
                inputs=[str(source)], output=str(tmp_path / "missing" / "out.docx")
            )
        )


def test_output_overwriting_input_rejected(source: Path) -> None:
    with pytest.raises(CommandBuildError, match="Output would overwrite an input file"):
        build_command(PandocTask(inputs=[str(source)], output=str(source)))


def test_output_that_is_an_existing_directory_rejected(
    tmp_path: Path, source: Path
) -> None:
    directory = tmp_path / "out.docx"
    directory.mkdir()

    with pytest.raises(CommandBuildError, match="Output path is a directory"):
        build_command(PandocTask(inputs=[str(source)], output=str(directory)))


@pytest.mark.parametrize(
    ("field_name", "label"),
    [
        ("template", "Template file"),
        ("reference_doc", "Reference document"),
        ("csl", "CSL file"),
    ],
)
def test_missing_path_option_files_rejected(
    tmp_path: Path, source: Path, output: Path, field_name: str, label: str
) -> None:
    with pytest.raises(CommandBuildError, match=f"{label} does not exist"):
        build_command(
            task_for(source, output, **{field_name: str(tmp_path / "missing.file")})
        )


def test_missing_bibliography_file_rejected(
    tmp_path: Path, source: Path, output: Path
) -> None:
    with pytest.raises(CommandBuildError, match="Bibliography file does not exist"):
        build_command(
            task_for(source, output, bibliography=[str(tmp_path / "missing.bib")])
        )


def test_missing_resource_path_directory_rejected(
    tmp_path: Path, source: Path, output: Path
) -> None:
    with pytest.raises(CommandBuildError, match="Resource path does not exist"):
        build_command(
            task_for(source, output, resource_path=[str(tmp_path / "missing-dir")])
        )


def test_resource_path_must_be_a_directory(
    tmp_path: Path, source: Path, output: Path
) -> None:
    resource_file = tmp_path / "resource.txt"
    resource_file.write_text("data", encoding="utf-8")

    with pytest.raises(CommandBuildError, match="Resource path is not a directory"):
        build_command(task_for(source, output, resource_path=[str(resource_file)]))


def test_allowed_extra_option_with_arity_is_passed_through(
    source: Path, output: Path
) -> None:
    command = build_command(
        task_for(source, output, extra_options=["--columns", "80", "--section-divs"])
    )

    assert command[1:4] == ["--columns", "80", "--section-divs"]
    assert command[-3:] == [
        "-o",
        str(output.resolve()),
        str(source.resolve()),
    ]


def test_unknown_extra_option_rejected(source: Path, output: Path) -> None:
    with pytest.raises(CommandBuildError, match="Unsupported extra option"):
        build_command(task_for(source, output, extra_options=["--evil"]))


def test_extra_option_missing_arity_rejected(source: Path, output: Path) -> None:
    with pytest.raises(CommandBuildError, match="requires 1 value"):
        build_command(task_for(source, output, extra_options=["--columns"]))


def test_extra_option_value_starting_with_dash_rejected(
    source: Path, output: Path
) -> None:
    with pytest.raises(CommandBuildError, match="must not start with '-'"):
        build_command(task_for(source, output, extra_options=["--columns", "-x"]))


def test_positional_extra_option_token_rejected(source: Path, output: Path) -> None:
    with pytest.raises(CommandBuildError, match="Invalid extra option token"):
        build_command(task_for(source, output, extra_options=["80"]))


@pytest.mark.parametrize(
    "forbidden",
    [
        ["--filter", "evil"],
        ["--lua-filter", "evil.lua"],
        ["--pdf-engine-opt", "-x"],
        ["--data-dir", "/tmp"],
    ],
)
def test_program_options_are_not_expressible(
    source: Path, output: Path, forbidden: list[str]
) -> None:
    with pytest.raises(CommandBuildError, match="Unsupported extra option"):
        build_command(task_for(source, output, extra_options=forbidden))


def test_describe_allowed_extra_options_lists_long_names() -> None:
    description = describe_allowed_extra_options()

    assert "--columns" in description
    assert "--epub-cover-image" in description
    assert "--section-divs" in description
    for dangerous in ("--filter", "--lua-filter", "--pdf-engine-opt", "--data-dir"):
        assert dangerous not in description


@pytest.mark.parametrize(
    "engine", ["pdflatex", "xelatex", "lualatex", "typst", "weasyprint"]
)
def test_allowed_pdf_engines_are_emitted(
    source: Path, output: Path, engine: str
) -> None:
    command = build_command(task_for(source, output, pdf_engine=engine))

    assert command[1:3] == ["--pdf-engine", engine]


def test_highlight_style_is_emitted(source: Path, output: Path) -> None:
    command = build_command(task_for(source, output, highlight_style="zenburn"))

    assert command[1:3] == ["--highlight-style", "zenburn"]


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc is not installed")
def test_real_pandoc_markdown_to_html(tmp_path: Path) -> None:
    media_source = tmp_path / "smoke.md"
    media_source.write_text("# Smoke\n\nHello.\n", encoding="utf-8")
    media_output = tmp_path / "smoke.html"

    command = build_command(
        PandocTask(inputs=[str(media_source)], output=str(media_output), standalone=True)
    )
    subprocess.run(command, check=True, capture_output=True)

    assert media_output.is_file()
