# -*- coding: utf-8 -*-
# Copyright (c) 2004-2014 Alterra, Wageningen-UR
# Allard de Wit (allard.dewit@wur.nl), April 2014
import re

from ..exceptions import PCSEError

class XYPairsError(PCSEError):
    pass

class LengthError(PCSEError):
    pass

class DuplicateError(PCSEError):
    pass

def _remove_whitespace(filecontents):
    """
    Remove whitespace (space, newline) from all lines.
    """
    return [line.strip(" \n\r") for line in filecontents]

def _remove_empty_lines(filecontents):
    """
    Return only non-empty ("") lines.
    """
    return [line for line in filecontents if len(line) > 0]

def _remove_inline_comments(filecontents):
    """
    Remove inline comments (marked by a !) from all lines.
    """
    return [line.split("!")[0] for line in filecontents]

def _is_comment(line):
    return line.startswith("*")

def _find_header(filecontents):
    """
    Splits a file into its header, which has lines starting with '*'
    at the beginning of the file, and its body, which is the rest of
    the file. Further lines marked with '*' are deleted.
    """
    # Find the first line that is not a comment
    line_is_comment = [_is_comment(line) for line in filecontents]
    try:
        body_start = line_is_comment.index(False)
    except ValueError:
        msg = "No body text found, only header"
        raise PCSEError(msg)

    # Split the file into header and body
    header = filecontents[:body_start]
    body = filecontents[body_start:]

    # Remove comments from the body
    body = [line for line in body if not _is_comment(line)]

    return header, body

def _find_parameter_sections(body):
    """
    Sort the body text into string, table, and scalar variables.
    """
    # Find lines belonging to each category
    scalars, strings, tables = [], [], []
    for line in body:
        if "'" in line: # string parameter
            strings.append(line)
        elif "," in line: # table parameter
            tables.append(line)
        else:
            scalars.append(line)

    # Convert the lists of variables into strings
    scalars, strings, tables = (" ".join(data) for data in (scalars, strings, tables))

    return scalars, strings, tables

# Regular expressions for parsing scalar, table and string parameters
_re_scalar = "[a-zA-Z0-9_]+[\s]*=[\s]*[a-zA-Z0-9_.\-]+"
_re_table = "[a-zA-Z0-9_]+[\s]*=[\s]*[0-9,.\s\-+]+"
_re_string = "[a-zA-Z0-9_]+[\s]*=[\s]*'.*?'"

def _find_individual_pardefs(regexp, parsections):
    """
    Splits the string into individual parameter definitions.
    """
    # Split the string
    par_definitions = re.findall(regexp, parsections)

    # Check for parameters that were not parsed correctly
    rest = re.sub(regexp, "", parsections)  # Remove pardefs from string
    rest = rest.replace(";", "").strip()  # Remove ; and whitespace
    if len(rest) > 0:
        msg = ("Failed to parse the CABO file!\n"
              f"Found the following parameter definitions:\n {par_definitions}\n"
              f"But failed to parse:\n '{rest}'")
        raise PCSEError(msg)

    return par_definitions

def _parse_scalar_pardef(parstr):
    """
    Parse a scalar parameter definition into a (key, value) pair.
    """
    try:
        parname, valuestr = parstr.split("=")
        if "." in valuestr:
            value = float(valuestr)
        else:
            value = int(valuestr)
    except ValueError:
        msg = f"Failed to parse parameter string: '{parstr}'"
        raise PCSEError(msg)

    parname = parname.strip()
    return (parname, value)

def _parse_string_pardef(parstr):
    """
    Parse a string parameter definition into a (key, value) pair.
    """
    try:
        parname, valuestr = parstr.split("=", 1)
        value = valuestr.replace("'", "").replace('"', "")
    except ValueError:
        msg = f"Failed to parse parameter string: '{parstr}'"
        raise PCSEError(msg)

    parname = parname.strip()
    return (parname, value)

def _parse_table_pardef(parstr):
    """
    Parses table parameter into a list of floats.
    """
    try:
        parname, valuestr = parstr.split("=")
    except ValueError:
        msg = f"Failed to parse parameter string: '{parstr}'"
        raise PCSEError(msg)

    parname = parname.strip()
    valuestrings = valuestr.split(",")

    # Check if the data match length/shape requirements
    n_valuestrings = len(valuestrings)
    if n_valuestrings < 4:
        msg = (f"Failed to parse table parameter '{parname}': '{valuestr}'\n"
                "Table parameters should contain at least 4 values.\n"
               f"Instead found {n_valuestrings} values.")
        raise LengthError(msg)
    if (n_valuestrings % 2) != 0:
        msg = (f"Failed to parse table parameter '{parname}': '{valuestr}'\n"
                "Table parameters should contain an even number of values.\n"
               f"Instead found {n_valuestrings} values.")
        raise XYPairsError(msg)

    table = [float(v) for v in valuestrings]

    return (parname, table)


class CABOFileReader(dict):
    """Reads CABO files with model parameter definitions.

    The parameter definitions of Wageningen crop models are generally
    written in the CABO format. This class reads the contents, parses
    the parameter names/values and returns them as a dictionary.

    :param fname: parameter file to read and parse
    :returns: dictionary like object with parameter key/value pairs.

    Note that this class does not yet fully support reading all features
    of CABO files. For example, the parsing of booleans, date/times and
    tabular parameters is not supported and will lead to errors.

    The header of the CABO file (marked with ** at the first line) is
    read and can be retrieved by the get_header() method or just by
    a print on the returned dictionary.

    *Example*

    A parameter file 'parfile.cab' which looks like this::

        ** CROP DATA FILE for use with WOFOST Version 5.4, June 1992
        **
        ** WHEAT, WINTER 102
        ** Regions: Ireland, central and southern UK (R72-R79),
        **          Netherlands (not R47), northern Germany (R11-R14)
        CRPNAM='Winter wheat 102, Ireland, N-U.K., Netherlands, N-Germany'
        CROP_NO=99
        TBASEM   = -10.0    ! lower threshold temp. for emergence [cel]
        DTSMTB   =   0.00,    0.00,     ! daily increase in temp. sum
                    30.00,   30.00,     ! as function of av. temp. [cel; cel d]
                    45.00,   30.00
        ** maximum and minimum concentrations of N, P, and K
        ** in storage organs        in vegetative organs [kg kg-1]
        NMINSO   =   0.0110 ;       NMINVE   =   0.0030

    Can be read with the following statements::

        >>>fileparameters = CABOFileReader('parfile.cab')
        >>>print fileparameters['CROP_NO']
        99
        >>>print fileparameters
        ** CROP DATA FILE for use with WOFOST Version 5.4, June 1992
        **
        ** WHEAT, WINTER 102
        ** Regions: Ireland, central and southern UK (R72-R79),
        **          Netherlands (not R47), northern Germany (R11-R14)
        ------------------------------------
        CROP_NO: 99 <class 'int'>
        TBASEM: -10.0 <class 'float'>
        NMINSO: 0.011 <class 'float'>
        NMINVE: 0.003 <class 'float'>
        CRPNAM: Winter wheat 102, Ireland, N-U.K., Netherlands, N-Germany <class 'str'>
        DTSMTB: [0.0, 0.0, 30.0, 30.0, 45.0, 30.0] <class 'list'>
    """
    def __init__(self, fname):
        # Read the file
        with open(fname) as fp:
            filecontents = fp.readlines()

        # Cleanup: remove in-line comments, whitespace, empty lines
        filecontents = _remove_inline_comments(filecontents)
        filecontents = _remove_whitespace(filecontents)
        filecontents = _remove_empty_lines(filecontents)

        if len(filecontents) == 0:
            msg = "Empty CABO file!"
            raise PCSEError(msg)

        # Split between file header and parameters
        self.header, body = _find_header(filecontents)

        # Find parameter sections using string methods
        scalars, strings, tables = _find_parameter_sections(body)

        # Parse into individual parameter definitions
        scalar_defs = _find_individual_pardefs(_re_scalar, scalars)
        string_defs = _find_individual_pardefs(_re_string, strings)
        table_defs = _find_individual_pardefs(_re_table, tables)

        # Parse individual parameter definitions into name & value.
        scalar_pars = [_parse_scalar_pardef(d) for d in scalar_defs]
        string_pars = [_parse_string_pardef(d) for d in string_defs]
        table_pars = [_parse_table_pardef(d) for d in table_defs]

        # Assign resulting values to the dictionary
        self.update(scalar_pars + string_pars + table_pars)

    def __str__(self):
        msg = ""
        for line in self.header:
            msg += line+"\n"
        msg += "------------------------------------\n"
        for key, value in self.items():
            msg += ("%s: %s %s\n" % (key, value, type(value)))
        return msg
