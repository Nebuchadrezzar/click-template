"""
Allow multiple chaining cmd: https://click.palletsprojects.com/en/7.x/commands/#multi-command-pipelines
and https://github.com/pallets/click/tree/master/examples/imagepipe
credits: https://github.com/pallets
"""
import os
from ast import literal_eval
from functools import update_wrapper
from typing import Dict

import click
import pandas as pd

CONFIG = {
    "read_functions": {".csv": pd.read_csv, ".xlsx": pd.read_excel},
    "to_functions"  : {
        ".csv" : lambda df, **kwargs: df.to_csv(kwargs.pop("buf"), **kwargs),
        ".xlsx": lambda df, **kwargs: df.to_excel(kwargs.pop("buf"), **kwargs)
    }
}


@click.group(chain=True)
def cli():
    """CLI
    """


@cli.result_callback()
def process_commands(processors):
    """This result callback is invoked with an iterable of all the chained
    subcommands.  As in this example each subcommand returns a function
    we can chain them together to feed one into the other, similar to how
    a pipe on unix works.
    """
    # Start with an empty iterable.
    stream = ()

    # Pipe it through all stream processors.
    for processor in processors:
        stream = processor(stream)

    # Evaluate the stream and throw away the items.
    for _ in stream:
        pass


def processor(f):
    """Helper decorator to rewrite a function so that it returns another
    function from it.
    """

    def new_func(*args, **kwargs):
        def processor(stream):
            try:
                result = f(stream, *args, **kwargs)
                return result
            except Exception as e:
                click.echo(f"Error: {e}", err=True)

        return processor

    return update_wrapper(new_func, f)


def generator(f):
    """Similar to the :func:`processor` but passes through old values
    unchanged and does not pass through the values as parameter.
    """

    @processor
    def new_func(stream, *args, **kwargs):
        yield from stream
        yield from f(*args, **kwargs)

    return update_wrapper(new_func, f)


def args_to_dict(arg: str) -> Dict:
    """
    Allows one to parse a string and try to interpret it from cli option format: "name_param=value|name_param=value"
    and return a dict
    """
    params_asdict = {}
    if arg:
        params = arg.split("|")
        for p in params:
            splitted = p.split("=")
            try:
                params_asdict[splitted[0]] = literal_eval(
                    splitted[1])  # try to interpret the string for instance "True" -> True
            except Exception:
                params_asdict[splitted[0]] = splitted[1]  # fallback to string
    return params_asdict


@cli.command("read")
@click.option(
    "-f",
    "--filename",
    type=click.Path(),
    required=True,
    help="filename to convert to a pandas data frame",
)
@click.option(
    "-p",
    "--params",
    type=str,
    default='',
    help="string representing params forwarded to pd.read function in format: 'name_param=value|name_param=value'",
)
@generator
def read_cmd(filename, params):
    """
    Read one file and convert it to a pandas dataframe.
    Pandas read function are called under the hood thanks to a mapping with file extension.
    """
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"{filename} not found.")

    if os.path.isfile(filename):
        fname, fextension = os.path.splitext(filename)
        read_func = CONFIG["read_functions"]
        pd_params = args_to_dict(params) if params else {}
        df = read_func[fextension](filename, **pd_params)
        yield df


@cli.command("head")
@click.option("-l", "--lines", default=5, type=int, help="Number of lines to print in stdout")
@processor
def head_cmd(dfs, lines):
    """
    Print to stdout the specified num of @lines starting from the top of the dataframe.
    """
    for df in dfs:
        click.echo(df.head(lines))
        yield


@cli.command("filter")
@click.option("-e", "--expression", required=True, type=str,
              help="a string expression forwarded to pd.query see: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.query.html")
@processor
def filter_cmd(dfs, expression):
    """
    Execute a pd.query with @expression to the dataframe.
    https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.query.html
    """
    for df in dfs:
        df = df.query(expression)
        print(df)
        yield df


@cli.command("to")
@click.option("-f", "--filename", type=click.Path())
@click.option("-p", "--params", type=str, default='',
              help="string representing the params to be forwarded to the pd.to function in format: 'name_param=value|name_param=value'")
@processor
def to_cmd(dfs, filename, params):
    """
    Export dataframe, according to @filename extension and forward @params to the pd.to function associated.
    Currently, the supported extensions : .xlsx: to_excel | .csv: to_csv | .html: to_html
    """
    for df in dfs:
        fname, fextension = os.path.splitext(filename)
        to_func = CONFIG["to_functions"][fextension]
        pd_params = args_to_dict(params) if params else {}
        to_func(df, buf=filename, **pd_params)
        yield


@cli.command("info")
@processor
def info_cmd(dfs):
    """
    Execute a pd.info on the dataframe
    """
    for df in dfs:
        click.echo(df.info())
        yield


@cli.command("print")
@processor
def info_cmd(dfs):
    """
    Print all the rows of a dataframe
    """
    for df in dfs:
        pd.set_option('display.max_rows', df.shape[0] + 1)
        click.echo(df.to_string(index=False))
        yield