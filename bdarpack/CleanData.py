from bdarpack import utils_ as ut_
import pandas as pd
import numpy as np
import pprint
import os
import logging
import re
import math
from copy import deepcopy

class CleanData:
    """
    Class for cleaning data
    Inputs:
        definitions (loaded global definitions)

    Change Log:
        (MZ): 17-08-2023: added generation of initial report (modified options in Dictionary)
    """

    def __init__(self,
        definitions=None,
        debug=True
    ):
        
        self.debug = debug

        self.nanList = ["","#N/A","#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null "] #(MZ): 28-02-2024

        # LOADING DEFAULTS
        self.folder_rawData = "rawData"
        self.folder_trainData = "trainData"
        self.read_na = False #(MZ): 28-02-2024

        self.output_type_data = 'csv'
        self.output_type_dict = 'xlsx'

        self.initial_report_filename = 'initial_report.xlsx' #output file name to store the initial report prior to optional cleaning steps

        self.logging = True
        self.log_filename = "logfile.txt" #output file name to store logs

        self.create_unique_index = False #whether to create a unique index for clean_df
        self.unique_index_composition_list = []
        self.unique_index_delimiter = "_"

        self.dict_var_varname = "NAME" # column in data dictionary containing variable names in input data
        self.dict_var_varcategory = "CATEGORY" # column in data dictionary setting the category of the variable name
        self.dict_var_varsecondary = "SECONDARY" # column in data dictionary setting if the variable is a secondary variable  #(MZ): 12-04-2024
        self.dict_var_varfrequency = "FREQUENCY" # column in data dictionary setting the frequency of the variable (for longitudinal datasets). #(MZ): 16-04-2024
        self.dict_var_type = "TYPE" # column in data dictionary setting the type of variable (string, numeric, date, bool)
        self.dict_var_codings = "CODINGS" # column in data dictionary setting the codings of variable (dataformat, categories)
        self.var_name_stripemptyspaces = False #If True, empty spaces will be stripped from variable names in input data, and from variables names listed in data dictionary.
        self.longitudinal_variableMarker = None #column header which contains the list of categories stipulating a list of longitudinal markers
        self.longitudinal = False # boolean indicating if the data is longitudinal   #(MZ): 16-04-2024
        self.longitudinal_freq_set_dict = {} # list of variables for each frequency #(MZ): 16-04-2024

        # LOADING DEFAULTS FOR SECONDARY VARIABLE REMOVAL
        self.options_secondary_removal_exclude_list = [] # secondary variables to exclude from removal process  #(MZ): 16-04-2024

        # LOADING DEFAULTS FOR DUPLICATED ROWS
        self.dropped_duplicated_rows_filename = "rowsRemoved.xlsx"
        self.suffix_dropped_duplicated_rows = "DD"

        # LOADING DEFAULTS FOR STANDARDISE TEXT
        self.suffix_standardise_text = "ST"
        self.options_standardise_text_case_type = "uppercase"
        self.options_standardise_text_exclude_list = []
        self.options_standardise_text_case_type_dict = {}

        # LOADING DEFAULTS FOR STANDARDISE DATES
        self.suffix_standardise_date = "DATE"
        self.options_standardise_date_format = "yyyy-mm-dd"
        self.options_faileddate_conversions_filename = 'failed_date_conversions.csv'

        # LOADING DEFAULTS FOR ASCII CONVERSION
        self.suffix_convert_ascii = "ASCII"
        self.options_convert_ascii_exclusion_list = []

        # LOADING DEFAULTS FOR CONSTRAINTS
        self.suffix_constraints = "CON"

        # LOADING DEFAULTS FOR REMOVING SECONDARY VARIABLES
        self.suffix_remove_secondary = "NOSEC"
        self.output_removed_secondary_filename = "removed_secondary_variables.xlsx"

        # LOAD DEFINITIONS
        self.definitions = definitions
        self._load_definitions()

        # LOAD INPUT DATA
        self.read_inputData(sheetname=self.definitions.RAWXLSX_SHEETNAME)

        # LOAD DATA DICTIONARY
        self.read_inputDict(sheetname=self.definitions.RAWDICTXLSX_SHEETNAME)

        # CHECK IF THE VARIABLES IN INPUT DATA MATCHES THE DATA DICTIONARY
        no_mismatch = self._check_variable_match_dict_data(strip_empty_spaces=self.var_name_stripemptyspaces)
        if not no_mismatch:
            print(f"Mismatched Variables:\n {self.var_diff_list}")

        # GET LIST OF LONGITUDINAL MARKERS.
        self._get_longitudinal_marker_list()

        # GET CATEGORY: FIELD DICTIONARY
        self._get_field_category_from_dict()
        
        # GET TYPE: FIELD DICTIONARY
        self._get_dataType_from_dict()

        # CLEAN NUMERIC NANS
        if self.read_na:
            self._clean_numeric_na() #(MZ): 28-02-2024 need to clean numeric fields if na strings are loaded

        # CREATE UNIQUE INDEX #(MZ): 20-03-2024: add option to customise unique row index
        if self.create_unique_index:
            self.fn_create_unique_index()
        

        # SAVE NEW DATA AND DICTIONARY IN TRAINDATA PATH
        self._save_data_to_file()
        self._save_dict_to_file()

        # Generate Report (initial, prior to optional steps)
        self.gen_data_report(data=self.clean_df, dict=self.clean_dict_df)

        
    def fn_create_unique_index(self): #(MZ): 20-03-2024: add function to customise unique row index from existing columns
        df = deepcopy(self.clean_df)
        uic_list = self.unique_index_composition_list
        delimiter = self.unique_index_delimiter

        for col in uic_list:
            if (col not in df.columns):
                raise ValueError("Dataframe does not contain column " + col)

        df['new_index'] = df.apply(
            lambda row: delimiter.join(
                [str(row[col]) for col in uic_list] + [str(row.name)]
            ),
            axis=1
        )
        df.set_index('new_index', drop=True, inplace=True)

        self.clean_df = deepcopy(df)

        return self.clean_df

    def _update_defaults(self, var_to_update, new_value):
        if hasattr(self.definitions, new_value):
            attr = getattr(self.definitions, new_value)
            if attr is not None:
                setattr(self, var_to_update, attr)

    def _load_definitions(self):

        # Updating defaults
        self._update_defaults(var_to_update="logging", new_value="LOGGING")
        self._update_defaults(var_to_update="log_filename", new_value="LOG_FILENAME")
        self._update_defaults(var_to_update="folder_rawData", new_value="RAW_PATH")
        self._update_defaults(var_to_update="folder_trainData", new_value="TRAIN_PATH")
        self._update_defaults(var_to_update="read_na", new_value="READ_NA") #(MZ): 28-02-2024
        self._update_defaults(var_to_update="dict_var_varname", new_value="DICT_VAR_VARNAME")
        self._update_defaults(var_to_update="dict_var_varcategory", new_value="DICT_VAR_VARCATEGORY") #(MZ): 12-04-2024
        self._update_defaults(var_to_update="dict_var_varsecondary", new_value="DICT_VAR_VARSECONDARY")
        self._update_defaults(var_to_update="dict_var_varfrequency", new_value="DICT_VAR_VARFREQUENCY")
        self._update_defaults(var_to_update="dict_var_type", new_value="DICT_VAR_TYPE")
        self._update_defaults(var_to_update="dict_var_codings", new_value="DICT_VAR_CODINGS")
        

        self._update_defaults(var_to_update="create_unique_index", new_value="CREATE_UNIQUE_INDEX")
        self._update_defaults(var_to_update="unique_index_composition_list", new_value="UNIQUE_INDEX_COMPOSITION_LIST")
        self._update_defaults(var_to_update="unique_index_delimiter", new_value="UNIQUE_INDEX_DELIMITER")
        
        self._update_defaults(var_to_update="var_name_stripemptyspaces", new_value="VAR_NAME_STRIPEMPTYSPACES")
        
        # Updating defaults for OUTPUT TYPES
        self._update_defaults(var_to_update="output_type_data", new_value="OUTPUT_TYPE_DATA")
        self._update_defaults(var_to_update="output_type_dict", new_value="OUTPUT_TYPE_DICT")

        # Updating defaults for REPORTS
        self._update_defaults(var_to_update="initial_report_filename", new_value="INITIAL_REPORT_FILENAME")

        # Updating defaults for SECONDARY VARIABLES REMOVAL
        self._update_defaults(var_to_update="options_secondary_removal_exclude_list", new_value="OPTIONS_SECONDARY_REMOVAL_EXCLUDE_LIST")  #(MZ): 16-04-2024

        # Updating defaults for DROP DUPLICATES
        self._update_defaults(var_to_update="dropped_duplicated_rows_filename", new_value="OUTPUT_DROPPED_DUPLICATED_ROWS_FILENAME")
        self._update_defaults(var_to_update="suffix_dropped_duplicated_rows", new_value="SUFFIX_DROPPED_DUPLICATED_ROWS")

        # Updating defaults for STANDARDISE TEXT
        self._update_defaults(var_to_update="suffix_standardise_text", new_value="SUFFIX_STANDARDISE_TEXT")
        self._update_defaults(var_to_update="options_standardise_text_case_type", new_value="OPTIONS_STANDARDISE_TEXT_CASE_TYPE")
        self._update_defaults(var_to_update="options_standardise_text_exclude_list", new_value="OPTIONS_STANDARDISE_TEXT_EXCLUDE_LIST")
        self._update_defaults(var_to_update="options_standardise_text_case_type_dict", new_value="OPTIONS_STANDARDISE_TEXT_CASE_TYPE_DICT")

        # Updating defaults for STANDARDISE DATES
        self._update_defaults(var_to_update="suffix_standardise_date", new_value="SUFFIX_STANDARDISE_DATE")
        self._update_defaults(var_to_update="options_standardise_date_format", new_value="OPTIONS_STANDARDISE_DATE_FORMAT")
        self._update_defaults(var_to_update="options_faileddate_conversions_filename", new_value="OPTIONS_FAILEDDATE_CONVERSIONS_FILENAME")

        # Updating defaults for CONVERTING ASCII
        self._update_defaults(var_to_update="suffix_convert_ascii", new_value="SUFFIX_CONVERT_ASCII")
        self._update_defaults(var_to_update="options_convert_ascii_exclusion_list", new_value="OPTIONS_CONVERT_ASCII_EXCLUSION_LIST")

        self._update_defaults(var_to_update="suffix_constraints", new_value="SUFFIX_CONSTRAINTS")

        # Updating defaults for REMOVING SECONDARY VARIABLES
        self._update_defaults(var_to_update="suffix_remove_secondary", new_value="SUFFIX_REMOVE_SECONDARY")
        self._update_defaults(var_to_update="output_removed_secondary_filename", new_value="OUTPUT_REMOVED_SECONDARY_FILENAME")


        self.prefix_path = self.definitions.PREFIX_PATH
        self.prefix_path = self.prefix_path.replace("\\","/")

        self.raw_data_path = self.prefix_path + self.folder_rawData + "/"
        self.raw_data_path = self.raw_data_path.replace("\\","/")

        self.raw_data_filename = self.raw_data_path + self.definitions.RAWXLSX
        self.raw_data_filename = self.raw_data_filename.replace("\\","/")

        self.raw_data_dict_filename = self.raw_data_path + self.definitions.RAWDICTXLSX
        self.raw_data_dict_filename = self.raw_data_dict_filename.replace("\\","/")

        self.train_data_path = self.prefix_path + self.folder_trainData + "/"
        self.train_data_path = self.train_data_path.replace("\\","/")

        # CREATE REQUIRED FOLDERS
        # (MZ): 18-03-2024: fix bug where required folders not available prior to logging
        if not os.path.exists(self.train_data_path):
            os.makedirs(self.train_data_path)

        # LOADING DEFAULTS FOR LOG FILE
        if (self.logging):
            self.log_filepath = self.prefix_path + self.folder_trainData + "/" + self.log_filename
            self.log_filepath = self.log_filepath.replace("\\","/")
            
            logging.basicConfig(filename=self.log_filepath, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

            self.logger = logging.getLogger(__name__)
            self.logger.debug('CleanData initialising...')
        else:
            self.log_filepath = None
            self.logger = None


        # Initialise filename for reports
        self.initial_report_filename = self.train_data_path + self.initial_report_filename

        # Initialise latest_filename for cleaned input data
        self.data_latest_filename = self.train_data_path + self.definitions.RAWXLSX
        self.data_latest_filename = ut_.change_extension(self.data_latest_filename, self.output_type_data)

        # Initialise latest filename for data dictionary
        self.dict_latest_filename = self.train_data_path + self.definitions.RAWDICTXLSX
        self.dict_latest_filename = ut_.change_extension(self.dict_latest_filename, self.output_type_dict)

        # Initialise latest filename for split-datasets
        self.latest_filename_split_dict = {} # (MZ): 16-04-2024: 
        self.latest_filename_split_merged = None #filename for merged split-dataframe into big dataframe based on crossgroupindex

        # Initialise settings for longitudinal data
        self._update_defaults(var_to_update="longitudinal_variableMarker", new_value="LONG_VAR_MARKER")

        self.longitudinal_marker_list = None #list of longitudinal markers
        
        self.raw_df = None #initialise raw data (dataframe)
        self.dict_df = None #initialise data dictionary (dataframe)
        self.clean_df = None #initialise cleaned data (dataframe)
        self.clean_dict_df = None #initialise cleaned data dictionary (dataframe)
        self.clean_split_df = {} #initialise cleaned data, split into groups (dataframe)
        self.var_list = None #list of all variables (column headers) found in input data
        self.var_diff_list = None #list of discrepancies between data dictionary and input data
        self.cat_var_dict = None #dictionary with {cat: [list of variables]}
        self.var_secondary_list = None #list of secondary variables
        self.type_var_dict = None #dictionary with {type: [list of variables]}
        self.report_df = None #initialise the report (dataframe) prior to optional cleaning steps

    def convert_2_dtypes(self, data):
        """Convert data (df) into best possible dtypes"""
        return data.convert_dtypes()
    
    def add_dictionary_row(self, row_attributes):
        """Add a new entry to the data dictionary."""
        
        dict_temp = deepcopy(self.clean_dict_df)
        new_df = pd.DataFrame(row_attributes, index=[0])
        dict_temp = pd.concat([dict_temp, new_df], ignore_index=True)

        self.clean_dict_df = deepcopy(dict_temp)
        self._save_dict_to_file()

        return

    def _get_longitudinal_marker_list(self):
        """
        Updates the longitudinal_marker_list using the longitudinal_variableMarker column in raw_df.
        
        Parameters
        ----------
        self : an instance of the Preprocessing class
        
        Returns
        -------
        longitudinal_marker_list : a list of longitudinal markers
        """  

        if self.longitudinal_variableMarker is not None:
            self.longitudinal_marker_list = list(self.raw_df[self.longitudinal_variableMarker].unique())
            self.longitudinal_marker_list.sort() #(MZ): 16-04-2024 add sort
            self.longitudinal = True    #(MZ): 16-04-2024
        else:
            self.longitudinal_marker_list = ["0"]
        
        if (self.debug):
            print(f"Extracting list of longitudinal markers: {self.longitudinal_marker_list}")
        if (self.logging):
            self.logger.info(f"Extracting list of longitudinal markers: {self.longitudinal_marker_list}")

    def _get_longitudinal_freq_set(self):
        """
        Get a dictionary of frequencies, and its corresponding set of variables
        """

        #(MZ): 16-04-2024

        if self.longitudinal_marker_list is None:
            self._get_longitudinal_marker_list()

        if self.longitudinal:
            for freq in self.longitudinal_marker_list:
                self.longitudinal_freq_set_dict[freq] = []
        
        if self.clean_dict_df is not None:
            A = self.dict_var_varname
            B = self.dict_var_varfrequency
            freq_df = self.clean_dict_df[[A,B]]

            for freq in self.longitudinal_marker_list:
                names = []

                for index, row in freq_df.iterrows():
                    if freq in row[B]:
                        names.append(row[A])
                
                self.longitudinal_freq_set_dict[freq] = names

    
    def read_inputData(self, sheetname=None):
        """Reads raw data from input definitions and outputs it as a dataframe.
        Data can be in the following formats:
            a) Excel .xlsx
            b) Text .csv
        
        Parameters
        ----------
        sheetname : string, optional
            Name of the sheet in the excel file. If not specified, the first sheet will be read.
        
        Returns
        -------
        raw_df : pandas dataframe
            Dataframe containing the raw data.
        """

        # (MZ): 23-02-2024: fix undefined self.raw_data_sheetname if input not xlsx

        if (self.debug):
            print(f"Reading raw data from filename: {self.raw_data_filename}")
        if (self.logging):
            self.logger.info(f"Reading raw data from filename: {self.raw_data_filename}")

        # Check if file exists
        if not ut_.check_filename(self.raw_data_filename):
            raise FileNotFoundError(f"File {self.raw_data_filename} cannot be found.")

        # Get filename extension
        extension = ut_.get_extension(self.raw_data_filename)
        if (self.debug):
            print(f"File extension: {extension}")
        if (self.logging):
            self.logger.info(f"File extension: {extension}")
        
        # Get file_type
        try:
            if (extension=='xlsx'):
                file_type = 'excel'
                sheetnames = ut_.get_worksheet_names(self.raw_data_filename)
                if sheetname is None: # if sheetname is not given
                    sheetname = sheetnames[0] #read the first sheet

                    if (self.debug):
                        print(f"No sheetname given: sheetname assigned as {sheetname}.")
                    if (self.logging):
                        self.logger.info(f"No sheetname given: sheetname assigned as {sheetname}.")
                else:
                    if (self.debug):
                        print(f"Sheetname is preassigned as {sheetname}.")
                    if (self.logging):
                        self.logger.info(f"Sheetname is preassigned as {sheetname}.")
                
            elif (extension=='csv'):
                file_type = 'csv'

            self.raw_data_sheetname = sheetname
                        
        except ValueError as e:
            if self.logging:
                self.logger.error("Error in getting sheetname of file type xlsx: " + str(e))
            raise ValueError("Error in getting sheetname of file type xlsx: " + str(e)) from None
            

        try:
            if file_type=='excel':
                # Read file and output as dataframe
                with open(self.raw_data_filename, "rb") as f:
                    self.raw_df = pd.read_excel(f, sheet_name=sheetname)
                # self.raw_df = pd.read_excel(self.raw_data_filename,
                #     sheet_name=sheetname
                # )
            elif file_type=='csv':
                # Read file and output as dataframe
                if self.read_na:
                    self.raw_df = pd.read_csv(self.raw_data_filename, na_values=None, keep_default_na=False) #(MZ): 27022024: switch to preserve user defined 'na'
                else:
                    self.raw_df = pd.read_csv(self.raw_data_filename)
                
        except ValueError as e:
            if self.logging:
                self.logger.error('Could not read sheet in excel file: ' + str(e))
            raise ValueError('Could not read sheet in excel file: ' + str(e)) from None
        
        if (self.debug):
            print(f"Input data loaded.")
        if (self.logging):
            self.logger.info(f"Input data loaded.")

        return self.raw_df

    def read_inputDict(self, sheetname=None):
        """This function reads a raw data dictionary (currently only supports .xlsx files) and returns it as a dataframe. 
        If no sheetname is given the first sheet of the file is assumed.
        
        Parameters
        ----------
        sheetname : str
            name of sheet to be read from .xlsx file.
            
        Returns
        -------
        self.dict_df : pandas.dataframe
            dataframe containing raw data dictionary.
        
        """

        # (MZ): 23-02-2024: fix undefined self.raw_data_dict_sheetname if input not xlsx

        if (self.debug):
            print(f"Reading data dictionary from filename: {self.raw_data_dict_filename}")
        if (self.logging):
            self.logger.info(f"Reading data dictionary from filename: {self.raw_data_dict_filename}")

        # Check if file exists
        if not ut_.check_filename(self.raw_data_dict_filename):
            raise FileNotFoundError(f"File {self.raw_data_dict_filename} cannot be found.")
        
        # Get filename extension
        extension = ut_.get_extension(self.raw_data_dict_filename)
        if (self.debug):
            print(f"File extension: {extension}")
        if (self.logging):
            self.logger.info(f"File extension: {extension}")

        # Get file_type
        try:
            if (extension=='xlsx'):
                file_type = 'excel'
                sheetnames = ut_.get_worksheet_names(self.raw_data_dict_filename)
                if sheetname is None: # if sheetname is not given
                    sheetname = sheetnames[0] #read the first sheet

                    if (self.debug):
                        print(f"No sheetname given: sheetname assigned as {sheetname}.")
                    if (self.logging):
                        self.logger.info(f"No sheetname given: sheetname assigned as {sheetname}.")
                else:
                    if (self.debug):
                        print(f"Sheetname is preassigned as {sheetname}.")
                    if (self.logging):
                        self.logger.info(f"Sheetname is preassigned as {sheetname}.")
            
            self.raw_data_dict_sheetname = sheetname
                        
        except ValueError as e:
            if self.logging:
                self.logger.error("Error in getting sheetname of file type xlsx: " + str(e))
            raise ValueError("Error in getting sheetname of file type xlsx: " + str(e)) from None
        
        try:
            if file_type=='excel':
                # Read file and output as dataframe
                with open(self.raw_data_dict_filename, "rb") as f:
                    self.dict_df = pd.read_excel(f, sheet_name=sheetname)
                # self.dict_df = pd.read_excel(self.raw_data_dict_filename,
                #     sheet_name=sheetname
                # )
        except ValueError as e:
            if self.logging:
                self.logger.error('Could not read sheet in excel file: ' + str(e))
            raise ValueError('Could not read sheet in excel file: ' + str(e)) from None
        
        if (self.debug):
            print(f"Data dictionary loaded.")
        if (self.logging):
            self.logger.info(f"Data dictionary loaded.")

        return self.dict_df
    
    def _clean_numeric_na(self):
        # (MZ): 28-02-2024: for var classed as numeric/bool (in dict), remove str type def of 'nan' based on self.nanList. Then cast column to its best possible dtype.

        if self.type_var_dict is None:
            self._get_field_category_from_dict()

        if (self.debug):
            print("Cleaning up str-type 'nan' in numeric/bool columns.")
        if (self.logging):
            self.logger.info("Cleaning up str-type 'nan' in numeric/bool columns.")

        df = deepcopy(self.clean_df)

        for col_name in self.type_var_dict['numeric']:
            df[col_name] = df[col_name].replace(self.nanList, value = np.nan)
            try:
                df[col_name] = df[col_name].astype(float)
                df[col_name] = df[col_name].convert_dtypes()
            except:
                if (self.debug):
                    print(f"{col_name} set as numeric, but could not be converted to float/int datatype.")
                if (self.logging):
                    self.logger.info(f"{col_name} set as numeric, but could not be converted to float/int datatype.")

        for col_name in self.type_var_dict['bool']:
            df[col_name] = df[col_name].replace(self.nanList, value = np.nan)
            try:
                df[col_name] = df[col_name].astype(float)
                df[col_name] = df[col_name].convert_dtypes()
            except:
                if (self.debug):
                    print(f"{col_name} set as numeric, but could not be converted to float/int datatype.")
                if (self.logging):
                    self.logger.info(f"{col_name} set as numeric, but could not be converted to float/int datatype.")

        self.clean_df = deepcopy(df)

        return self.clean_df

    
    def gen_data_report(self, data, dict, report_filename=None):
        # (MZ): 23-02-2024: added fix to strip trailing spaces in data_type_in_dict column
        # (MZ): 23-02-2024: added fix to check if col exists in `data` in Populate data list for objects
        # (MZ): 23-02-2024: updated function to allow varying data_types in dictionary
        # (MZ): 11-09-2024: added optional parameter: `report_filename`, default is `None`. Use relative path, such as 'report.xlsx'. The report will be saved in the self.train_data_path folder. If not specified, will use self.initial_report_filename as default filename.

        report_cols = ['data_type','data_type_in_dict','data_type_mismatch', 'count_missing_values', 'percentage_missing_values']
        report_df = pd.DataFrame(columns=report_cols, index=data.columns) #initialise dataframe B (not efficient)

        for col in data.columns:
            report_df.loc[col, 'data_type'] = str(data[col].dtype) #add datatype information

        for datatype_dict, data_type_set_var in self.type_var_dict.items():
            for set_var in data_type_set_var:
                report_df.loc[set_var, 'data_type_in_dict'] = str(datatype_dict).strip()
        
        # Check for possible datatype mismatch
        report_df['data_type_mismatch'] = "Possible mismatch"

        numerical_type_list = ["numeric", "Numeric", "Numerical", "numerical"]
        for i in numerical_type_list:
            report_df.loc[(report_df['data_type_in_dict'] == i) & 
                (report_df['data_type'].isin(['int32', 'Int32', 'int64', 'Int64', 'float64', 'Float64', 'timedelta[ns]'])),'data_type_mismatch'] = 'Matched'
        
        string_type_list = ["string", "String"]
        for i in string_type_list:
            report_df.loc[(report_df['data_type_in_dict'] == i) & 
              (report_df['data_type'].isin(['category', 'object', 'string'])),'data_type_mismatch'] = 'Matched'
        
        date_type_list = ["Date", "date"]
        for i in date_type_list:
            report_df.loc[(report_df['data_type_in_dict'] == i) & 
              (report_df['data_type'].isin(['datetime64', 'object'])),'data_type_mismatch'] = 'Matched'
        
        bool_type_list = ["bool", "Bool", "Boolean", "boolean"]
        for i in bool_type_list:
            report_df.loc[(report_df['data_type_in_dict'] == i) & 
              (report_df['data_type'].isin(['bool'])),'data_type_mismatch'] = 'Matched'
        
        # Check for number of missing values
        count_missing_values = data.isnull().sum()
        percentage_missing_values = data.isnull().mean()
        report_df = report_df.assign(count_missing_values=count_missing_values)
        report_df = report_df.assign(percentage_missing_values=percentage_missing_values)

        # Populate data range
        def f_range(col_name):
            if col_name in data:
                mini = str(data[str(col_name)].min())
                maxi = str(data[str(col_name)].max())
                return "[" + mini + "," + maxi + "]"
            else:
                return np.nan
        # for i in numerical_type_list:
        f = lambda row: f_range(row.name) if (row['data_type'] in (['Int32', 'Int64', 'Float64', 'int32', 'int64','float64'])) else np.nan
        report_df['numeric_range'] = report_df.apply(f, axis=1)

        # Populate data list for objects
        def f2(col_name):
            if col_name in data:
                list_unqiue = data[str(col_name)].unique()
                if len(list_unqiue)<20:
                    return '; '.join(str(v) for v in list_unqiue)
                else:
                    return 'Too many'
            else:
                return 'N.A.'
            
        f3 = lambda row: f2(row.name) if (row['data_type_in_dict'] in string_type_list) else "N.A."
        report_df['unique_categories'] = report_df.apply(f3, axis=1)

        # Inspect data range (MZ): 27-02-2024
        # create "codings_in_dict" column in report_df
        # report_df["codings_in_dict"] = [dict[dict["NAME"] == name][self.dict_var_codings].values[0] for name in report_df.index]
        report_df["codings_in_dict"] = [dict[dict["NAME"] == name][self.dict_var_codings].values[0] if dict[dict["NAME"] == name][self.dict_var_codings].values else "" for name in report_df.index]
        
        #check for CODINGS format type: [number,number] and (number,number)
        # pattern = r"\(|\[([\d]+),\s*([\d]+)\)|\(|\[([\d]+),\s*([\d]+)\]|\(|\[([\d]+),\s*([\d]+)\]"
        pattern = r"[\(\[](-?\d*\.?\d+),\s*(-?\d*\.?\d+)[\)\]]" # new regex accepts decimal places
        fn_numeric_range_check_bool = lambda row: "check_true" if (re.match(pattern, str(row['codings_in_dict']))) else "check_false"
        report_df['numeric_range_check_bool'] = report_df.apply(fn_numeric_range_check_bool, axis=1)

        # check for CODINGS format type: delimited by '; '
        def fn_str_list_check_bool(col_coding):
            if (';' in str(col_coding)):
                return "check_true"
            else:
                return "check_false"
        f_str_code = lambda row: fn_str_list_check_bool(row.codings_in_dict) if (row['numeric_range_check_bool']=="check_false") else "check_false"
        report_df['str_list_check_bool'] = report_df.apply(f_str_code, axis=1)

        # check for out-of-range numerical values
        def fn_build_numeric_range_error_list(col_name, col_coding):
            lower = ""
            higher = ""
            if col_name in data:
                # build max, min condition from dict_coding
                if ("[" in col_coding):
                    lower = "<="
                elif ("(" in col_coding):
                    lower = "<"
                if ("]" in col_coding):
                    higher = "<="
                elif (")" in col_coding):
                    higher = "<"
                temp_col_coding = str(col_coding).replace("[", "").replace("]", "").replace("(", "").replace(")", "")
                split_temp_col_coding = temp_col_coding.split(",")
                max_col_coding = higher + str(split_temp_col_coding[1])
                min_col_coding = str(split_temp_col_coding[0]) + lower

                def conv(x):
                    if isinstance(x, (int, float)):
                        ouput = str(x)
                        if type(x) == float:
                            x_temp = float(x)
                            if math.isnan(x_temp): #if nan, return ouput within range so that it is not flagged out as out-of-range.
                                # ouput = str(int(split_temp_col_coding[0]) + 1) #fix for floats #(MZ): 20-03-2025
                                ouput = str((float(split_temp_col_coding[0]) + float(split_temp_col_coding[1])) / 2)
                    elif isinstance(x, str):
                        try:
                            x_float = float(x)
                            ouput = str(x_float)
                        except:
                            # ouput = str(int(split_temp_col_coding[0]) + 1) #fix for floats #(MZ): 20-03-2025
                            ouput = str((float(split_temp_col_coding[0]) + float(split_temp_col_coding[1])) / 2)
                    else:
                        ouput = str(int(split_temp_col_coding[1]) + 1)
                    return ouput

                if self.create_unique_index: #(MZ): 20-03-2024
                    subject_ids = data[data[col_name].apply(lambda x:  not eval(min_col_coding + conv(x) + max_col_coding))].index.tolist()
                elif 'subject_id' in self.var_list: #works for TIMS ETL
                    subject_ids = data[data[col_name].apply(lambda x:  not eval(min_col_coding + conv(x) + max_col_coding))]['subject_id'].tolist()
                else: #if subject_id does not exist, save index
                    subject_ids = data[data[col_name].apply(lambda x:  not eval(min_col_coding + conv(x) + max_col_coding))].index.tolist()

                return ','.join(str(x) for x in subject_ids)
            else:
                return "col_name not in data"

        f4 = lambda row: fn_build_numeric_range_error_list(row.name, row.codings_in_dict) if (row['numeric_range_check_bool']=="check_true") else "N.A."
        report_df['numeric_range_error_list'] = report_df.apply(f4, axis=1)

        def fn_build_str_list_error_list(col_name, col_coding):

            if col_name in data:
                col_coding_list = col_coding.split(";")
                col_coding_list = list(map(str.strip, col_coding_list))

                def ss(x):
                    if isinstance(x,str):
                        if (x in col_coding_list):
                            return False
                        else: 
                            return True
                    elif isinstance(x, (int, float)):
                        if ((x*10 % 10) == 0):
                            num = int(x)
                        else: num = x
                        if (str(num) in col_coding_list):
                            return False
                        else:
                            return True
                    else:
                        return True

                if self.create_unique_index: #(MZ): 20-03-2024
                    subject_ids = data[data[col_name].apply(lambda x: ss(x) )].index.tolist()
                elif 'subject_id' in self.var_list: #works for TIMS ETL
                    subject_ids = data[data[col_name].apply(lambda x: ss(x) )]['subject_id'].tolist()
                else: #if subject_id does not exist, save index
                    subject_ids = data[data[col_name].apply(lambda x: ss(x) )].index.tolist()

                return ','.join(str(x) for x in subject_ids)
            else: 
                return "col_name not in data"

        f5 = lambda row: fn_build_str_list_error_list(row.name, row.codings_in_dict) if (row['str_list_check_bool']=="check_true") else "N.A."
        report_df['str_list_error_list'] = report_df.apply(f5, axis=1)

        # Save to class
        self.report_df = report_df

        # Save to file
        # (MZ): 11-09-2024
        if report_filename is None:
            report_filename = self.initial_report_filename
        else:
            report_filename = self.train_data_path + report_filename
        try:
            self._save_df_to_file(report_df, report_filename,sheetname='by Variable')
            if (self.debug):
                print(f"Initial Report Generated: filename: {report_filename}")
            if (self.logging):
                self.logger.info(f"Initial Report Generated: filename: {report_filename}")
        except:
            if (self.debug):
                print(f"Initial Report Generation FAILED.")
            if (self.logging):
                self.logger.info(f"Initial Report Generation FAILED.")
            return 0

        return 1

    def _check_variable_match_dict_data(self, strip_empty_spaces=False):
        """Check if variables in dictionary match the field headers in self.raw_df. Problematic fields will be stored in self.var_diff_list.
        
        Parameters
        ----------
        strip_empty_spaces : bool (default=False)
            Boolean determining whether or not to strip empty spaces in both the raw_df and dict_df.

        Returns
        -------
        bool
            Returns True if no variable mismatches, False otherwise.
        
        """

        # Load the variables names found in the data dictionary
        if self.dict_var_varname not in self.dict_df.columns:
            raise KeyError(f"Column {self.dict_var_varname} cannot be found in Data Dictionary. Please check that the the column exists in the Data Dictionary or specify the correct column name in the definitions.py file, under DICT_VAR_VARNAME.")

        # STRIP EMPTY SPACES
        if (strip_empty_spaces):
            self.clean_df = deepcopy(self.raw_df)
            self.clean_dict_df = deepcopy(self.dict_df)
            self.clean_df = ut_.strip_empty_spaces(self.clean_df)
            self.clean_dict_df = ut_.strip_empty_spaces(self.clean_dict_df)
            ut_.strip_string_spaces(self.clean_dict_df, col=self.dict_var_varname) #string spaces are not automatically stripped from data (prevent auto conversion to dates)
        else: 
            self.clean_df = deepcopy(self.raw_df)
            self.clean_dict_df = deepcopy(self.dict_df)

        # Load the column headers in self.clean_df
        var_clean_df_list = list(self.clean_df.columns)

        # Load the variables names found in the data dictionary
        var_dict_df_list = self.clean_dict_df[self.dict_var_varname].values.tolist()

        # Check if the variables in input data and dictionary matches
        self.var_diff_list = set(var_clean_df_list) ^ set(var_dict_df_list)

        # Save the list of variables if no discrepancies
        if (len(self.var_diff_list)==0):
            self.var_list = var_clean_df_list
            if (self.debug):
                print(f"No variable name mismatches found. Proceeding with next step of initialisation...")
            if (self.logging):
                self.logger.info(f"No variable name mismatches found. Proceeding with next step of initialisation...")
        else:
            self.var_list = var_clean_df_list #(MZ): 28-02-2024: list is still saved despite discrepancies
            print("There is a mismatch in the variable names extracted from the input data and the data dictionary. Use cleanData.var_diff_list to extract list of mismatched variable names.")
            if (self.logging):
                self.logger.info("There is a mismatch in the variable names extracted from the input data and the data dictionary. Use cleanData.var_diff_list to extract list of mismatched variable names.")
        
        return len(self.var_diff_list)==0

    def _save_df_to_file(self, df, filename, sheetname='Sheet1', index=True):

        file_ext = ut_.get_extension(filename)

        if (file_ext=='csv'):
            ut_.save_df_as_csv(df, filename, index=index)

        elif (file_ext=='xlsx'):
            ut_.save_df_as_excel(df, 
                excel_file_name = filename, 
                sheet_name = sheetname,
                index = index # saving the index or not
            )

        else:
            if self.logging:
                self.logger.error(f"Not able to save data to file for extension type: {file_ext}")
            raise ValueError(f"Not able to save data to file for extension type: {file_ext}")

    def _save_data_to_file(self):
        """Function to save data to file.
        This function saves the clean_df data frame to a CSV file or XLSX file depending on the file's extension. 
        
        Parameters
        ----------
        self : object
            The DataPipeline object which contains data frames and file locations.
        """

        file_ext = ut_.get_extension(self.data_latest_filename)

        if (file_ext=='csv'):
            ut_.save_df_as_csv(self.clean_df, self.data_latest_filename, index=False)

        elif (file_ext=='xlsx'):
            ut_.save_df_as_excel(self.clean_df, 
                excel_file_name = self.data_latest_filename, 
                sheet_name = self.raw_data_sheetname,
                index = False # not saving the index
            )

        else:
            if self.logging:
                self.logger.error(f"Not able to save data to file for extension type: {file_ext}")
            raise ValueError(f"Not able to save data to file for extension type: {file_ext}")

    def _save_dict_to_file(self):
        """Save the current clean_dict_df DataFrame to the latest filename with the corresponding extension type (ie: .csv, .xlsx)."""

        file_ext = ut_.get_extension(self.dict_latest_filename)

        if (file_ext=='csv'):
            ut_.save_df_as_csv(self.clean_dict_df, self.dict_latest_filename, index=False)
        
        elif (file_ext=='xlsx'):
            ut_.save_df_as_excel(self.clean_dict_df,
                excel_file_name = self.dict_latest_filename,
                sheet_name = self.raw_data_dict_sheetname,
                index = False # not saving the index
            )

        else:
            if self.logging:
                self.logger.error(f"Not able to save dictionary to file for extension type: {file_ext}")
            raise ValueError(f"Not able to save dictionary to file for extension type: {file_ext}")
        
    def update_data(self, new_df, filename_suffix=""):
        """
        Update the input data in the CleanData class with new input data and overwrite the previous version.
        
        Parameters
        ----------
        new_df (pandas Dataframe): The new data to replace old data in this class.
        filename_suffix (str, optional): An optional suffix added to the output file when data is saved. Default is ""
        
        """

        if (self.debug):
            print(f"Replacing the input data...")
        if (self.logging):
            self.logger.info(f"Replacing the input data...")
        
        try:
            # Get new filename
            old_filename = deepcopy(self.data_latest_filename)
            self.data_latest_filename = ut_.update_filename_with_suffix(filename=self.data_latest_filename, suffix=filename_suffix)

            # Update latest clean df to output_df
            old_df = deepcopy(self.clean_df)
            self.clean_df = deepcopy(new_df)
            if not self.create_unique_index:
                self.clean_df.reset_index(drop=True, inplace=True) #reset the index

            self._save_data_to_file()

            if (self.debug):
                print(f"Replacing the input data complete. new filename: {self.data_latest_filename}")
            if (self.logging):
                self.logger.info(f"Replacing the input data complete. new filename: {self.data_latest_filename}")
        except:
            self.data_latest_filename = deepcopy(old_filename) # return
            self.clean_df = deepcopy(old_df) # return

            if self.logging:
                self.logger.error(f"Not able to save data to file.")
            raise ValueError(f"Not able to save data to file.")

        
    def _get_list_of_secondaryVariables_from_dict(self):
        """
        Extracts a list of variables from the data dictionary, which are indicated as secondary variables.

        Parameters
        ----------
        self : object, instance of the dataframe   

        Returns
        -------
        var_secondary_list : list
            list of secondary variables
        
        #(MZ): 12-04-2024
        """

        A = self.dict_var_varname
        B = self.dict_var_varsecondary
        sec_df = self.clean_dict_df[[A,B]]

        self.var_secondary_list = list(sec_df[A][sec_df[B] == "Y"])

        return self.var_secondary_list

    def _get_field_category_from_dict(self):
        """
        Extracts dataframe columns with variable name and variable category and creates a dictionary with the categories as keys and the respective variables as values.
        
        Parameters
        ----------
        self : object, instance of the dataframe   
        
        Returns
        -------
        type_var_dict : dictionary
            dictionary with the categories as keys and the respective variables as values.
        """

        # Extract dataframe columns with variable name and variable category
        A = self.dict_var_varname
        B = self.dict_var_varcategory
        cat_df = self.clean_dict_df[[A, B]]

        # Create a dictionary
        self.cat_var_dict = {key: list(cat_df[A][cat_df[B] == key]) for key in cat_df[B].unique()}

    def _get_dataType_from_dict(self):
        """
        Extracts dataframe columns with variable name and variable type and 
        creates a dictionary with the type as keys and the respective variables 
        as values.
        
        Parameters
        ----------
        self : object, instance of the dataframe   
        
        Returns
        -------
        type_var_dict : dictionary
            dictionary with the variable type as keys and the respective variables as values.
        """
        # (MZ): 27022024: update to clean up varying categories
        # (MZ): 05092024: update to catch error where data dictionary has missing variable types

        # Extract dataframe columns with variable name and variable category
        A = self.dict_var_varname
        B = self.dict_var_type
        cat_df = self.clean_dict_df[[A, B]]

        # Create a dictionary
        temp_dict = {key: list(cat_df[A][cat_df[B] == key]) for key in cat_df[B].unique()}

        # Merge categories
        numerical_type_list = ["numeric", "Numeric", "Numerical", "numerical"]
        string_type_list = ["string", "String"]
        date_type_list = ["date", "Date"]
        bool_type_list = ["bool", "Bool", "Boolean", "boolean"]

        final_dict = {}
        numeric = []
        string = []
        date_type = []
        bool_type = []
        for key, value in temp_dict.items():
                            
            try: #(MZ): 05092024
                key_str = key.strip()
            except AttributeError as e:
                if self.logging:
                    self.logger.error(f'Some of the variables having missing/non-str variable types: {str(key)}. Please amend the data dictionary before proceeding' + str(e))
                raise Exception(f'Some of the variables have missing/non-str variable types: {str(key)}. Please amend the data dictionary before proceeding.' + str(e)) from None
            
            if key_str in numerical_type_list:
                numeric = numeric + value
            elif key_str in string_type_list:
                string = string + value
            elif key_str in date_type_list:
                date_type = date_type + value
            elif key_str in bool_type_list:
                bool_type = bool_type + value
            else:
                final_dict[key_str] = value
        final_dict['numeric'] = numeric
        final_dict['string'] = string
        final_dict['date'] = date_type
        final_dict['bool'] = bool_type

        self.type_var_dict = final_dict


    # DROP DUPLICATES
    def drop_duplicate_rows(self):
        """Use to drop duplicate rows from the input dataframe. Performs the following steps:
        1) Exclude variables of the "Index" category from the duplicate search
        2) Make a working copy of the input dataframe
        3) Get the index of duplicate rows
        4) Drop the duplicate rows from the dataframe
        5) Get the dropped rows from the original dataframe and save them as an excel file
        6) Update the new filename and the new input dataframe        
        """

        if (self.debug):
            print(f"Dropping duplicate rows in input data...")
        if (self.logging):
            self.logger.info(f"Dropping duplicate rows in input data...")

        # Exclude variables of the "Index"  category from the duplicate search
        subset_list = ut_.remove_items(self.cat_var_dict["Index"], self.var_list)

        # Get a working copy of latest data dataframe
        df = deepcopy(self.clean_df)

        # Get index of duplicate rows
        duplicated_index = df.duplicated(keep='first', subset=subset_list)

        # Drop duplicate rows
        output_df = df.drop_duplicates(subset=subset_list, keep='first', inplace=False)

        # Get the dropped rows from original dataframe
        dropped_rows_df = df.loc[duplicated_index]
        no_dropped_rows = dropped_rows_df.shape[0]
        
        if (self.debug):
            print(f"No. of dropped rows: {no_dropped_rows}")
        if (self.logging):
            self.logger.info(f"No. of dropped rows: {no_dropped_rows}")

        # Save dropped rows as excel file
        ut_.save_df_as_excel(dropped_rows_df,
            excel_file_name = self.train_data_path + self.dropped_duplicated_rows_filename,
            sheet_name = "Sheet1",
            index = True
        )

        # Update new filename and new input data
        self.update_data(new_df=output_df, filename_suffix=self.suffix_dropped_duplicated_rows)

    # STANDARDISE TEXT
    def standardise_text_case_conversion(self, data, case_type):
        """
        The standardise_text_case_conversion function takes dataframe (cols) and one case type parameter as input and returns the text data converted as per the case type specified.

        Parameters
        ----------
        data : pandas dataframe
            The columns of the dataframe should contain text as data type.
        case_type : str
            The case type should be specified as either uppercase, lowercase or capitalise.
                    
        Returns
        ---------
        pandas dataframe
        The dataframe with all the text values converted to one specified case type.
        """
        if case_type == 'uppercase':
            data = data.astype(str).str.upper()
        elif case_type == 'lowercase':
            data = data.astype(str).str.lower()
        elif case_type == 'capitalise':
            data = data.astype(str).str.title()

        return data

    def standardise_text(self):
        """
        Standardises text case in input data.

        Parameters
        ----------
        self: Module object
            Module object containing all the attributes and methods.
            
        Returns
        -------
        """

        if (self.debug):
            print(f"Standardising text in input data...")
        if (self.logging):
            self.logger.info(f"Standardising text in input data...")

        # Load case_type
        def_case_type = self.options_standardise_text_case_type #set default case_type
        exclude_list = self.options_standardise_text_exclude_list
        case_type_dict = self.options_standardise_text_case_type_dict

        # ExTRACT variables of the "Index"  category
        subset_list = self.cat_var_dict["Index"]

        # Get a working copy of latest data dataframe
        df = deepcopy(self.clean_df)

        # convert data_df to best possible dtypes
        output_df = self.convert_2_dtypes(df)

        # Loop through df and convert all strings to specified case
        for col in output_df.columns:
            if col not in subset_list: # exclude variables marked as index type
                if col not in exclude_list: # exclude varaibles in exclude_list

                    # Overwrite default case_type with specified type in dict
                    case_type = def_case_type
                    if col in case_type_dict:
                        case_type = case_type_dict[col]
                    
                    # Perform conversion
                    if output_df[col].dtype == 'object':
                        output_df[col] = self.standardise_text_case_conversion(output_df[col], case_type)
                    elif output_df[col].dtype == 'string':
                        output_df[col] = self.standardise_text_case_conversion(output_df[col], case_type)
        
        # Update new filename and new input data
        self.update_data(new_df=output_df, filename_suffix=self.suffix_standardise_text)

    # CONVERTING ASCII
    def converting_ascii(self, ascii_exclusion_list=None):
        """Converts all characters in input data to ASCII-compatible format

        Parameters
        ----------
        ascii_exclusion_list : list, default = self.options_convert_ascii_exclusion_list
            List of characters to not replace

        Returns
        -------
        self : object
            Returns self with clean_df updated with the ascii compatible data

        """

        # Load options
        ascii_exclusion_list = ascii_exclusion_list or self.options_convert_ascii_exclusion_list

        if (self.debug):
            print(f"Converting all characters to ASCII-compatible in input data...")
            print(f"List of Exclusions: \n{ascii_exclusion_list}")

        if (self.logging):
            self.logger.info(f"Converting all characters to ASCII-compatible in input data...")
            self.logger.info(f"List of Exclusions: \n{ascii_exclusion_list}")

        # Get a working copy of latest data dataframe
        df = deepcopy(self.clean_df)

        # convert data_df to best possible dtypes
        output_df = self.convert_2_dtypes(df)

        # replace all characters in list of exclusions
        list_of_cols_with_ex_char = []
        for col in output_df.columns:
            if output_df[col].dtype == object or output_df[col].dtype == "string":
                for ex_char in ascii_exclusion_list:
                    if any(ex_char in s for s in output_df[col] if not pd.isnull(s)): # (MZ): 22032024: to skip null values which are not iterable
                        replace_str = f"-~*{ex_char}*~-"
                        output_df[col] = output_df[col].str.replace(ex_char, replace_str, regex=False)
                        list_of_cols_with_ex_char.append(col)

        # convert all string/object columns to ascii-compatible characters
        output_df = ut_.convert_to_ascii(output_df)

        # revert all characters in list of exclusions
        for col in list_of_cols_with_ex_char:
            for ex_char in ascii_exclusion_list:
                replace_str = f"-~*{ex_char}*~-"
                replace_str = ut_.convert_to_ascii(replace_str)
                output_df[col] = output_df[col].str.replace(replace_str, ex_char, regex=False)


        # Update new filename and new input data
        self.update_data(new_df=output_df, filename_suffix=self.suffix_convert_ascii)

    # SPLIT DATASETS INTO LONGITUDINAL POINTS
    def split_longitudinal_by_group(self, options=[]):
        """
        Split datasets based on longitudinal visits.
        This function assumes that each row of the dataframe comprises variables associated with a specific visit of a single subject. Each subject can have multiple visits, i.e. multiple rows, and the dataframe contains rows originating from multiple subjects.

        Not all variables are relevant for all visits, and this information is recorded in the data dictionary, under self.dict_var_varfrequency column. The function uses self._get_longitudinal_freq_set to get a dictionary of frequencies (visits) and its corresponding set of variables.

        The original dataframe is split into separate dataframes, each corresponding to a specific visit. Then, irrelevant variables for that specific visit are removed. New filenames are created and stored in self.latest_filename_split_dict. Dataframes are then saved to file.

        if `merge` is `True`: merge the splitted dataframes into one big dataframe, based on `crossgroupindex`, such as the `subject_id`. Rename the variables with suffix `_<frequency>`, and merge the dataframes, with `baseline` on left. Save dataframe to file using suffix `-MERGED`.

        Parameters
        ----------
        options: (dict, optional). Dictionary of options that can change the behaviour of this method. Defaults to an empty dictionary.
            crossgroupindex (str, optional): The column to use for merging longitudinal visits. Defaults to None.
            baseline (str, optional): The baseline group for merging. Defaults to None.
            merge (bool, optional): Whether or not to merge the split dataframes. Defaults to False.
            var_sort_list (list, optional): Sorted list of variables. For sorting final_df according to given sequence. Variables not in `var_sort_list` will be dropped.

        Returns
        -------
        No value returned, updates the dataFile given.

        #(MZ): 16-10-2024
        """

        crossgroupindex = None
        baseline_group = None
        merge = False
        var_sort_list = None
        if "crossgroupindex" in options:
            crossgroupindex = options['crossgroupindex']
        if "baseline" in options:
            baseline_group = options['baseline']
        if "merge" in options:
            merge = options['merge']
        if "var_sort_list" in options:
            var_sort_list = options['var_sort_list']
        else:
            var_sort_list = self.var_list

        if (self.debug):
            print(f"Splitting dataset into longitudinal groupings...")

        if (self.logging):
            self.logger.info(f"Splitting dataset into longitudinal groupings...")

        # Get working copy of latest dataframe
        df = deepcopy(self.clean_df)

        # Create a new dataframe containing rows where "longvarmarker" equals the current value
        longvarmarker = self.longitudinal_variableMarker
        # Get set of variables for each frequency
        self._get_longitudinal_freq_set()
        freq_set_dict = self.longitudinal_freq_set_dict

        if (self.debug):
            print(f"Longitudinal variable: {longvarmarker}")

        if (self.logging):
            self.logger.info(f"Longitudinal variable: {longvarmarker}")
        
        if merge:
            split_df_dict, merged_df = ut_.split_longitudinal_by_group(
                df = df, 
                longvarmarker = longvarmarker, 
                longitudinal_marker_list = self.longitudinal_marker_list, 
                freq_set_dict = freq_set_dict, 
                options={
                    'merge':True,
                    'crossgroupindex': crossgroupindex,
                    'baseline_group': baseline_group,
                    'var_sort_list': var_sort_list
                }
            )

            # Save to file
            newfilename = ut_.update_filename_with_suffix(filename=self.data_latest_filename, suffix=f"{longvarmarker}-MERGED")
            self._save_df_to_file(
                df = merged_df,
                filename = newfilename,
                sheetname = 'Sheet1',
                index = False
            )
            self.latest_filename_split_merged = newfilename
        else:
            split_df_dict = ut_.split_longitudinal_by_group(
                df = df, 
                longvarmarker = longvarmarker, 
                longitudinal_marker_list = self.longitudinal_marker_list, 
                freq_set_dict = freq_set_dict, 
                options={
                    'merge':False,
                    'crossgroupindex': crossgroupindex,
                    'baseline_group': baseline_group,
                    'var_sort_list': var_sort_list
                }
            )

        # Save to class
        self.clean_split_df = deepcopy(split_df_dict)

        # Save to file
        # Initialise new filename
        self.latest_filename_split_dict[longvarmarker] = {}
        for value in self.longitudinal_marker_list:
            self.latest_filename_split_dict[longvarmarker][value] = ut_.update_filename_with_suffix(filename=self.data_latest_filename, suffix=value)

            self._save_df_to_file(
                df = split_df_dict[value],
                filename = self.latest_filename_split_dict[longvarmarker][value],
                sheetname = 'Sheet1',
                index = False
            )


    def split_longitudinal_by_visits(self, options={}):
        """
        Split datasets based on longitudinal visits.
        This function assumes that each row of the dataset comprises all variables associated with a single subject. All visits from a single subject are consolidated under a single row; the variables from different visits are differentiated using suffixes that can be detailed in self.longitudinal_marker_list.
        For reference, see: utils.split_longitudinal_by_visits.

        Parameters
        ----------
        options: (dict, optional). Dictionary of options that can change the behaviour of this method. Defaults to an empty dictionary.
            crossgroupindex (str, optional): The column to use for merging longitudinal visits. Defaults to None.
            merge (bool, optional): Whether or not to merge the split dataframes. Defaults to False.
            var_sort_list (list, optional): Sorted list of variables. For sorting final_df according to given sequence. Variables not in `var_sort_list` will be dropped.
            mandatory_variable (str, optional): Defaults to 'All'
            file_to_split (str, optional): full path of csv file to split. Defaults to self.latest_filename_split_merged.

        Returns
        -------
        No values returned, outputs to file.

        #(MZ): 16-10-2024
        """

        crossgroupindex = None
        merge = False
        var_sort_list = None
        mandatory_variable = 'All'
        file_to_split = None #full path of csv file to split
        if "crossgroupindex" in options:
            crossgroupindex = options['crossgroupindex']
        if "merge" in options:
            merge = options['merge']
        if "var_sort_list" in options:
            var_sort_list = options['var_sort_list']
        else:
            var_sort_list = self.var_list
        if "mandatory_variable" in options:
            mandatory_variable = options['mandatory_variable']
        if "file_to_split" in options:
            file_to_split = options['file_to_split']

        if (self.debug):
            print(f"Splitting dataset into longitudinal groupings...")

        if (self.logging):
            self.logger.info(f"Splitting dataset into longitudinal groupings...")

        if file_to_split is None:
            split_merged_filename = self.latest_filename_split_merged
        else:
            split_merged_filename = file_to_split
        split_merged_df = pd.read_csv(split_merged_filename, na_values=None, keep_default_na=False)

        longitudinal_marker_dict = {}
        for visit in self.longitudinal_marker_list:
            temp = visit.replace(" ", "_")
            longitudinal_marker_dict[visit] = f"_{temp}"

        if merge:
            split_df_dict, merged_df = ut_.split_longitudinal_by_visits(
                df = split_merged_df,
                longitudinal_marker_dict=longitudinal_marker_dict,
                crossgroupindex = crossgroupindex,
                options = {
                    'merge': True,
                    'mandatory_variable': mandatory_variable,
                    'var_sort_list': var_sort_list
                }
            )

            #  Save to file
            newfilename = ut_.update_filename_with_suffix(filename=split_merged_filename, suffix='MERGEDREV')
            self._save_df_to_file(
                df = merged_df,
                filename = newfilename,
                sheetname = 'Sheet1',
                index = False
            )
            self.latest_filename_split_merged = newfilename

        else:
            split_df_dict = ut_.split_longitudinal_by_visits(
                df = split_merged_df,
                longitudinal_marker_dict=longitudinal_marker_dict,
                crossgroupindex = crossgroupindex,
                options = {
                    'merge': False,
                    'mandatory_variable': mandatory_variable,
                    'var_sort_list': var_sort_list
                }
            )

        # Save to class
        self.clean_split_df = deepcopy(split_df_dict)

        # Save to file
        # Initialise new filename
        longvarmarker = self.longitudinal_variableMarker
        self.latest_filename_split_dict[longvarmarker] = {}
        for value in self.longitudinal_marker_list:
            cvalue = f"MERGEDREV-{value}"
            self.latest_filename_split_dict[longvarmarker][cvalue] = ut_.update_filename_with_suffix(filename=self.data_latest_filename, suffix=cvalue)

            self._save_df_to_file(
                df = split_df_dict[value],
                filename = self.latest_filename_split_dict[longvarmarker][cvalue],
                sheetname = 'Sheet1',
                index = False
            )
    


    def _split_longitudinal_on_visits(self, options={}):
        """
        Deprecated. Use split_longitudinal_by_group instead.
        Split datasets based on longitudinal visits.
        This function assumes that each row of the dataframe comprises variables associated with a specific visit of a single subject. Each subject can have multiple visits, i.e. multiple rows, and the dataframe contains rows originating from multiple subjects.

        Not all variables are relevant for all visits, and this information is recorded in the data dictionary, under self.dict_var_varfrequency column. The function uses self._get_longitudinal_freq_set to get a dictionary of frequencies (visits) and its corresponding set of variables.

        The original dataframe is split into separate dataframes, each corresponding to a specific visit. Then, irrelevant variables for that specific visit are removed. New filenames are created and stored in self.latest_filename_split_dict. Dataframes are then saved to file.

        if `merge` is `True`: merge the splitted dataframes into one big dataframe, based on `crossgroupindex`, such as the `subject_id`. Rename the variables with suffix `_<frequency>`, and merge the dataframes, with `baseline` on left. Save dataframe to file using suffix `-MERGED`.

        Parameters
        ----------
        options: (dict, optional). Dictionary of options that can change the behaviour of this method. Defaults to an empty dictionary.
            crossgroupindex (str, optional): The column to use for merging longitudinal visits. Defaults to None.
            baseline (str, optional): The baseline group for merging. Defaults to None.
            merge (bool, optional): Whether or not to merge the split dataframes. Defaults to False.

        Returns
        -------
        No value returned, updates the dataFile given.

        #(MZ): 12-04-2024
        """

        crossgroupindex = None
        baseline_group = None
        merge = False
        if "crossgroupindex" in options:
            crossgroupindex = options['crossgroupindex']
        if "baseline" in options:
            baseline_group = options['baseline']
        if "merge" in options:
            merge = options['merge']

        if (self.debug):
            print(f"Splitting dataset into longitudinal groupings...")

        if (self.logging):
            self.logger.info(f"Splitting dataset into longitudinal groupings...")

        # Get a working copy of the latest data dataframe
        df = deepcopy(self.clean_df)

        # create a new dataframe containing rows where "longvarmarker" equals the current value
        longvarmarker = self.longitudinal_variableMarker
        split_df_dict = {}
        self.latest_filename_split_dict[longvarmarker] = {}

        # Get set of variables for each frequency
        self._get_longitudinal_freq_set()
        freq_set_dict = self.longitudinal_freq_set_dict

        if (self.debug):
            print(f"Longitudinal variable: {longvarmarker}")

        if (self.logging):
            self.logger.info(f"Longitudinal variable: {longvarmarker}")

        for value in self.longitudinal_marker_list:
            # split into new dataframe
            split_df_dict[value] = df[df[longvarmarker] == value]

            # filter out variables based on freq_set_dict
            freq_set_list = freq_set_dict[value]
            full_var_list = list(split_df_dict[value].columns)
            common_var_list = list(set(freq_set_list).intersection(set(full_var_list)))

            common_var_list = ut_.sort_subset(common_var_list, self.var_list)

            split_df_dict[value] = split_df_dict[value][common_var_list]
            
            # initialise new filename
            self.latest_filename_split_dict[longvarmarker][value] = ut_.update_filename_with_suffix(filename=self.data_latest_filename, suffix=value)

            if (self.debug):
                print(f"Saving group: {value} to filename: {self.latest_filename_split_dict[longvarmarker][value]}")

            if (self.logging):
                self.logger.info(f"Saving group: {value} to filename: {self.latest_filename_split_dict[longvarmarker][value]}")

            # save to file
            self._save_df_to_file(
                df = split_df_dict[value],
                filename = self.latest_filename_split_dict[longvarmarker][value],
                sheetname = 'Sheet1',
                index=True
            )

            # save to class
            self.clean_split_df = deepcopy(split_df_dict)
            
        # Merge split-dataframe into big dataframe based on crossgroupindex
        if crossgroupindex is not None:
            for value in split_df_dict.keys():

                # assign first group as baseline if none
                if baseline_group is None:
                    baseline_group = value

                df_A = deepcopy(split_df_dict[value])
                value_strip_str = value.replace(" ", "_")
                # rename columns in dataframe by appending suffix
                for col in df_A.columns:
                    if col != crossgroupindex:
                        df_A = df_A.rename(columns={col: col + f"_{value_strip_str}"})

                split_df_dict[value] = deepcopy(df_A)

        if merge:
            # initialise new filename
            newfilename = ut_.update_filename_with_suffix(filename=self.data_latest_filename, suffix=f"{longvarmarker}-MERGED")
            if baseline_group is not None:
                merged_df = deepcopy(split_df_dict[baseline_group])

                for value in split_df_dict.keys():
                    if (value != baseline_group):
                        df_right = deepcopy(split_df_dict[value])

                        merged_df = pd.merge(merged_df, df_right, on=crossgroupindex, how='left')

            # save to file
            self._save_df_to_file(
                df = merged_df,
                filename = newfilename,
                sheetname = 'Sheet1',
                index=True
            )
            self.latest_filename_split_merged = newfilename


    def _split_longitudinal_on_visits_reverse(self, df, output_filename=None, options={}):
        """
        # Deprecated, in favour of ut_.split_longitudinal_on_group
        #(MZ): 06-05-2024
        """
        
        crossgroupindex = None
        baseline_group = None
        mandatory_var = None
        if "crossgroupindex" in options:
            crossgroupindex = options['crossgroupindex']
        if "baseline" in options:
            baseline_group = options['baseline']
        if "mandatory_var" in options:
            mandatory_var = options['mandatory_var']

        # Get working df
        split_merged_df = deepcopy(df)

        # Get set of variables for each frequency (freq_set_dict)
        merged_col_list = split_merged_df.columns.tolist() #full list of columns, with freq. as suffix
        freq_set_dict = {} #initialise dictionary
        for visit in self.longitudinal_marker_list:
            freq_set_dict[visit] = [crossgroupindex]
            for var in merged_col_list: #loop through full set of col. names with suffix
                value_strip_str = visit.replace(" ", "_")
                if value_strip_str in var: #put under proper key in freq_set_dict
                    freq_set_dict[visit].append(var)

        # Split working df into individual freq. df(s), store in dict `split_df_dict`
        split_df_dict = {} #initialise dictionary
        for key in freq_set_dict:
            temp_df = split_merged_df[freq_set_dict[key]] #build ind. df based on freq.
            value_strip_str = key.replace(" ", "_")
            for column in temp_df.columns: #replace column names
                new_column_name = column.replace(f'_{value_strip_str}', '')
                temp_df = temp_df.rename(columns={column: new_column_name})
            split_df_dict[key] = temp_df

        # Build final output df, final_df, by concatenating ind. df(s)
        for key in freq_set_dict:
            if key==baseline_group:
                final_df = split_df_dict[key]
            else:
                final_df = pd.concat([final_df, split_df_dict[key]])

        # Clean empty rows
        # Check if mandatory_var is empty. If empty, delete row
        if mandatory_var in final_df.columns:
            final_df = final_df[final_df[mandatory_var] != '']
            final_df = final_df.reset_index(drop=True) #reset dataframe index

        # Save to file
        if output_filename is not None:
            self._save_df_to_file(
                df = final_df,
                filename = output_filename,
                sheetname = 'Sheet1',
                index = True
            )
        
        return final_df
        

    # REMOVE SECONDARY VARIABLES
    def remove_secondary_variables(self):
        """
        Removes the secondary variable from the data

        Parameters
        ----------

        Returns
        -------
        No value returned, updates the dataFile given.

        #(MZ): 12-04-2024
        """

        if (self.debug):
            print(f"Removing secondary variables from input data...")
        if (self.logging):
            self.logger.info(f"Removing secondary variables from input data...")

        # Get list of secondary variables
        if (self.var_secondary_list is None):
            self._get_list_of_secondaryVariables_from_dict()

        # Get exclusion list
        exclusion_list = deepcopy(self.options_secondary_removal_exclude_list)

        if (self.debug):
            print(f"Removing exclusion list {exclusion_list} from list of secondary variables...")
        if (self.logging):
            self.logger.info(f"Removing exclusion list {exclusion_list} from list of secondary variables...")

        if (len(exclusion_list)>0): # remove excluded variables
            self.var_secondary_list = list(set(self.var_secondary_list) - set(exclusion_list))

        # Get a working copy of the latest data dataframe
        df = deepcopy(self.clean_df)

        # Drop secondary variables
        dropped_df = df[self.var_secondary_list]
        output_df = df.drop(self.var_secondary_list, axis=1)

        # Save dropped variables as excel file
        ut_.save_df_as_excel(dropped_df,
            excel_file_name = self.train_data_path + self.output_removed_secondary_filename,
            sheet_name = "Sheet1",
            index=True)
        
        # Update new filename and new input data
        self.update_data(new_df = output_df, filename_suffix = self.suffix_remove_secondary)
    
    # STANDARDISE DATES
    def standardise_date(self, def_date_format=None, faileddate_conversions_filename=None):
        """Standardises the date/time in input data.

        Standardise the date format of variables of the TYPE "date" (as specified in the data dictionary). Primarily changes the format of the column as per the predefined standard date and time format, as specified in OPTIONS_STANDARDISE_DATE_FORMAT (global definitions).

        It also stores the failed conversions in a csv file, as specified in OPTIONS_FAILEDDATE_CONVERSIONS_FILENAME (global definitions)
        
        Parameters
        ----------
        def_date_format : string, optional
            the standard date format to use for all dates (ignore if already specified in global definitions, default is 'yyyy-mm-dd') [follows format used in ms-excel, see ref. https://www.ablebits.com/office-addins-blog/change-date-format-excel/]

        faileddate_conversions_filename : string, optional
            the filename.csv for storing list of failed date conversions (ignore if already specified in global definitions, default is 'failed_date_conversions.csv') [only csv allowed]
        
        Returns
        -------
        No value returned, updates the dataFile given.
        """

        if (self.debug):
            print(f"Standardising date/time in input data...")
        if (self.logging):
            self.logger.info(f"Standardising date/time in input data...")

        # ExTRACT variables of the "Index"  category
        if 'Index' in self.cat_var_dict:
            index_list = self.cat_var_dict["Index"]
            chosen_index = index_list[0]
        else: 
            chosen_index = None

        # Load standardised date format
        def_date_format = def_date_format or self.options_standardise_date_format
        def_date_format_convert = ut_.mapping_dictDateFormatConversion(def_date_format)

        # Get list of variables defined as 'date' in TYPE
        dateVar_list = self.type_var_dict['date']

        # Get a working copy of latest data dataframe
        df = deepcopy(self.clean_df)

        # convert data_df to best possible dtypes
        output_df = self.convert_2_dtypes(df)

        # initialise empty dataframe to store failed conversions
        failedIndices_df = pd.DataFrame()
        faileddate_conversions_filename = faileddate_conversions_filename or self.options_faileddate_conversions_filename

        #
        for dateVar in dateVar_list:
            dateColFieldFormat = deepcopy(def_date_format_convert) # the date format to convert to

            # the date format to convert from
            raw_dateColFieldFormat = self.clean_dict_df[self.clean_dict_df[self.dict_var_varname]==dateVar][self.dict_var_codings].values[0]
            raw_dateColFieldFormat = ut_.mapping_dictDateFormatConversion(str(raw_dateColFieldFormat))
            
            # Conversion (Easiest Case [Excel])
            if output_df[dateVar].dtype == 'datetime64[ns]': # when raw excel column is specified as datatype: date in excel
                output_df[dateVar] = pd.to_datetime(output_df[dateVar], errors="ignore").dt.strftime(dateColFieldFormat)

            elif output_df[dateVar].dtype == 'string': # when column is specified as string

                # Check if date format is usable. If not, learn one from the data
                if raw_dateColFieldFormat == '' or raw_dateColFieldFormat=='nan':
                    if (self.debug):
                        print(f'Standardise date: raw_dateCOlFieldFormat for variable {dateVar} is not valid.')
                    if (self.logging):
                        self.logger.info(f'Standardise date: raw_dateCOlFieldFormat for variable {dateVar} is not valid.')

                    raw_dateColFieldFormat = ut_.date_format_search(output_df[dateVar])
                    if (self.debug):
                        print(f"Using {raw_dateColFieldFormat} as date format.")
                    if (self.logging):
                        self.logger.info(f"Using {raw_dateColFieldFormat} as date format.")

                # Conversion
                output_df = ut_.strip_string_spaces(output_df, col=dateVar)
                output_df[dateVar] = pd.to_datetime(output_df[dateVar], format=raw_dateColFieldFormat, errors="coerce").dt.strftime(dateColFieldFormat)

            # save failed conversions to dataframe
            if chosen_index is not None:
                temp_df = output_df[output_df[dateVar].isna()][chosen_index]
                # failedIndices_df[dateVar] = output_df[output_df[dateVar].isna()][chosen_index]
            else: # if chosen_index is not available, use df index
                temp_df = output_df[output_df[dateVar].isna()].index
                # failedIndices_df[dateVar] = output_df[output_df[dateVar].isna()].index

            temp_df.name = dateVar
            if failedIndices_df.empty:
                failedIndices_df[dateVar] = temp_df
            else:
                failedIndices_df = failedIndices_df.merge(temp_df, left_index=True, right_index=True, how='outer')

            if (self.output_type_data == 'csv'): #workaround to prevent automatic date conversion of csv by ms-excel
                output_df[dateVar] = ' ' + output_df[dateVar].astype(str) 

            # update dict 'CODINGS' column with new standardised date format
            self.clean_dict_df.loc[self.clean_dict_df[self.dict_var_varname]==dateVar, self.dict_var_codings] = def_date_format

        # Update new filename and new input data
        self.update_data(new_df=output_df, filename_suffix=self.suffix_standardise_date)

        # Update new data dictionary with new standardised date format
        self._save_dict_to_file()

        

        # Save failed conversions to file
        f_filename = self.train_data_path + faileddate_conversions_filename
        ut_.save_df_as_csv(failedIndices_df, f_filename, index=True)