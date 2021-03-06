import pandas as pd
from os import listdir, remove
from os.path import isfile, join
import re

import spacetrack.operators as op
from spacetrack import SpaceTrackClient
from datetime import datetime, timedelta

from tqdm import tqdm

def get_all_socrates_data(path):
    '''
    Builds a dataframe out of all the socrates data files
    
    Parameters:
    -----------
    path : str
        Relative file path of socrates files
    
    Returns
    -------
    df : Pandas Dataframe
        Combined set of all socrates data
    '''
    files = [ (match[0],match[1]) for f in listdir(path) if isfile(join(path, f))  if (match:=re.search('^socrates_([0-9]{14})\.csv(\.gz)?$', f))]
    files

    # Build single dataset
    df = pd.DataFrame()
    for file,date in tqdm(files):
        tmp_df = pd.read_csv(path + file)
        df = pd.concat([df,tmp_df])


    # Fix dates and timedeltas
    df['extract_date'] = pd.to_datetime(df['extract_date'], format='%Y-%m-%d %H:%M:%S.%f')
    df['start_time'] = pd.to_datetime(df['start_time'], format='%Y %b %d %H:%M:%S.%f')
    df['tca_time'] = pd.to_datetime(df['tca_time'], format='%Y %b %d %H:%M:%S.%f')
    df['stop_time'] = pd.to_datetime(df['stop_time'], format='%Y %b %d %H:%M:%S.%f')
    df['sat1_days_epoch'] = pd.to_timedelta(df['sat1_days_epoch'], 'd')
    df['sat2_days_epoch'] = pd.to_timedelta(df['sat2_days_epoch'], 'd')
    df['sat1_last_epoch'] = df['tca_time'] - df['sat1_days_epoch']
    df['sat2_last_epoch'] = df['tca_time'] - df['sat2_days_epoch']

    # Add "pair" column
    df['sat_pair'] = df.apply(lambda x: x['sat1_name'] + '-' + x['sat2_name'], axis=1)
    
    return df


socrates_group_num = 0
def get_socrates_cleaned_data(path):
    '''
    Builds a dataframe out of all the socrates data files
    and remove duplicates and sorts
    
    Parameters:
    -----------
    path : str
        Relative file path of socrates files
    
    Returns
    -------
    df : Pandas Dataframe
        Combined set of all socrates data
    '''
    
    def __set_group_number(x):
        global socrates_group_num
        if x:
            socrates_group_num += 1
        return socrates_group_num

    df = get_all_socrates_data(path)

    # Clean the data
    # Remove duplicates - keep the first occurence of a sat-pair and tca_time
    df = df.drop_duplicates(subset=['sat_pair', 'tca_time'], keep='first')

    # Set a group number (some entries have TCA times that change slightly and these will be grouped together)
    df = df.sort_values(['sat_pair','tca_time'])
    df['group'] = ((df['sat_pair'] != df['sat_pair'].shift(1)) | (df['tca_time']-df['tca_time'].shift(1) > pd.Timedelta('1 min'))).apply(__set_group_number)

    # Resort
    df = df.sort_values(['group','extract_date'])
    
    return df

def get_socrates_with_tle_data(df, tle_data_path):
    '''
    Merges the socrates data with the TLE data to create a new dataframe
    
    Parameters:
    -----------
    df : Pandas Dataframe
        The socrates dataframe
        
    tle_data_path : str
        Relative file path of TLE data
    
    Returns
    -------
    df : Pandas Dataframe
        Trimmed set of socrates data with TLE data (from file)
    '''
    # Get last row (most recent socrates record) of each group
    g = df.groupby('group')
    gdf = g.tail(1)

    # Open the TLE Pickle file and merge
    tle_df = pd.read_pickle(tle_data_path)
    gdf = gdf.merge(tle_df, left_on=['sat_pair','tca_time', 'sat1_norad', 'sat2_norad'], right_on=['sat_pair','tca_time', 'sat1_norad', 'sat2_norad'], how='left')
    
    return gdf
    
def get_all_socrates_and_tle_data(socrates_files_path, tle_file_path):
    '''
    Returns Socrates and TLE data joined together
    
    Parameters:
    -----------
    socrates_files_path : str
        Relative file path of socrates files
        
    tle_file_path : str
        Relative file path of TLE data
    
    Returns
    -------
    soc_df : Pandas Dataframe
        Socrates complete data
        
    tle_df : Pandas Dataframe
        Trimmed set of socrates data with TLE data (from file only)
    '''
    
    soc_df = get_socrates_cleaned_data(socrates_files_path)
    tle_df = get_socrates_with_tle_data(soc_df, tle_file_path)
    
    return soc_df, tle_df

def assign_socrates_category(df, detailed=False):
    '''
    Returns the dataframe with two new columns containing the sat1_name and sat2_name decoded
    to contain the sat1_cat and sat2_cat (category).
    
    Parameters:
    -----------
    df : Pandas Dataframe
        A socrates dataframe containing the sat1_name and sat2_name
        
    detailed : bool
        Returns the detailed category or a summary.  Summary contains only operational,
        nonoperational and unknown.
    
    Returns
    -------
    df : Pandas Dataframe
        Socrates dataframe passed in with 2 new columns: sat1_cat and sat2_cat
    '''
    
    def __detail_category(val):
        if val == '+':
            return 'Operational'
        elif val == 'P':
            return 'Paritally Operational'
        elif val == 'B':
            return 'Backup/Reserve'
        elif val == 'S':
            return 'New Spare'
        elif val == 'X':
            return 'Extended Mission'
        elif val == '-':
            return 'Nonoperational'
        elif val == 'D':
            return 'Decayed'
        else:
            return 'Unknown'
    
    if detailed:
        df['sat1_cat'] = df['sat1_name'].str[-2:-1].apply(__detail_category)
        df['sat2_cat'] = df['sat2_name'].str[-2:-1].apply(__detail_category)
    else:
        df['sat1_cat'] = df['sat1_name'].str[-2:-1].apply(lambda x: 'Operational' if x in ['+','P','B','S','X'] else ('Nonoperational' if x in ['-','D'] else 'Unknown'))
        df['sat2_cat'] = df['sat2_name'].str[-2:-1].apply(lambda x: 'Operational' if x in ['+','P','B','S','X'] else ('Nonoperational' if x in ['-','D'] else 'Unknown'))
    
    return df