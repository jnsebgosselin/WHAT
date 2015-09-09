# -*- coding: utf-8 -*-
"""
Copyright 2014-2015 Jean-Sebastien Gosselin
email: jnsebgosselin@gmail.com

This file is part of WHAT (Well Hydrograph Analysis Toolbox).

WHAT is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

#-- STANDARD LIBRARY IMPORTS --

import csv
from time import strftime, sleep
from os import getcwd
from copy import copy

#-- THIRD PARTY IMPORTS --

from PySide import QtCore
import numpy as np
from numpy.linalg import lstsq as linalg_lstsq

#-- PERSONAL IMPORTS --

import meteo
import database as db

#==============================================================================
class GapFillWeather(QtCore.QThread):
    """
    This functions is started on the GUI side when the *Fill* or *Fill All*
    button of the Tab named *Fill Data* is clicked on. It is the main routine
    that fill the missing data in the weather record.
    """
#==============================================================================
   
    # Definition of signals that can be used to easily add a Graphical User
    # Interface on top of this algorithm.
    
    ProgBarSignal = QtCore.Signal(int)
    ConsoleSignal = QtCore.Signal(str)
    EndProcess = QtCore.Signal(int)
    
    def __init__(self, parent=None):
        super(GapFillWeather, self).__init__(parent)
        
        #--------------------------------------------------- Required Inputs --
        
        self.time_start = 0
        self.time_end = 0
        self.WEATHER = []
        self.TARGET = []
        self.project_dir = getcwd()
        
        #------------------------------------------------- Method Parameters --
        
        self.Nbr_Sta_max = 4
        self.limitDist = 100
        self.limitAlt = 350
        
        self.regression_mode = True
        # --> if True = Ordinary Least Square
        # --> if False = Least Absolute Deviations
        
        self.STOP = False # Flag used to stop the Thread on the UI side
        
        self.add_ETP = False
        # If True, computes ETP from daily mean temperature time series with 
        # the function "calculate_ETP" from module "meteo" and add the results 
        # to the output datafile.
        
        self.full_error_analysis = False 
        # A complete analysis of the estimation errors is conducted with a
        # cross-validation procedure 
        # if *full_error_analysis* is *True*.
        
    def run(self): 
        
        #-------------------------------------------- Assign Local Variables --
        
        DATA = np.copy(self.WEATHER.DATA)

        DATE = np.copy(self.WEATHER.DATE)        
        YEAR, MONTH, DAY = DATE[:, 0], DATE[:, 1], DATE[:, 2]
        
        TIME = np.copy(self.WEATHER.TIME)
        index_start = np.where(TIME == self.time_start)[0][0]
        index_end = np.where(TIME == self.time_end)[0][0]
        
        VARNAME = self.WEATHER.VARNAME  # Name of the weather variables
        nVAR = len(VARNAME)  # Number of weather variables
        STANAME = np.copy(self.WEATHER.STANAME)
        CORCOEF = np.copy(self.TARGET.CORCOEF)
        
        HORDIST = np.copy(self.TARGET.HORDIST)
        ALTDIFF = np.copy(np.abs(self.TARGET.ALTDIFF))
        
        Nbr_Sta_max = self.Nbr_Sta_max
        limitDist = self.limitDist
        limitAlt = self.limitAlt
        
        #--------------------------------------------- Target Station Header --
        
        target_station_index = self.TARGET.index
        target_station_name = self.TARGET.name
        target_station_prov = self.WEATHER.PROVINCE[target_station_index]
        target_station_lat = self.WEATHER.LAT[target_station_index]
        target_station_lat = round(target_station_lat, 2)
        target_station_lon = self.WEATHER.LON[target_station_index]
        target_station_lon = round(target_station_lon, 2)
        target_station_alt = self.WEATHER.ALT[target_station_index]
        target_station_alt = round(target_station_alt, 2)
        target_station_clim = self.WEATHER.ClimateID[target_station_index]
        
        #----------------------------------------------------------------------
        
        # Save target data serie in a new 2D matrix that will
        # be filled during the data completion process
        Y2fill = np.copy(DATA[:, target_station_index, :])
        
        if self.full_error_analysis == True:
            YpFULL = np.copy(Y2fill) * np.nan
            print; print('A full error analysis will be performed'); print
        
        msg = 'Data completion for station %s started' % target_station_name
        print(msg)
        self.ConsoleSignal.emit('<font color=black>%s</font>' % msg)
        
        #--------------------------------------------- CHECK CUTOFF CRITERIA --        
        
        # Remove the neighboring stations that do not respect the distance
        # or altitude difference cutoffs.
        
        # If cutoff limits are set to a negative number, all stations are kept
        # regardless of their distance or altitude difference with the target
        # station.
        
        if limitDist > 0:
            check_HORDIST = HORDIST < limitDist
        else:
            check_HORDIST = np.zeros(len(HORDIST)) == 0 
            
        if limitAlt > 0:
            check_ALTDIFF = ALTDIFF < limitAlt
        else:
            check_ALTDIFF = np.zeros(len(ALTDIFF)) == 0
           
        check_ALL = check_HORDIST * check_ALTDIFF
        index_ALL = np.where(check_ALL == True)[0]                                  
       
        # Keep only the stations that respect all the treshold values
        
        STANAME = STANAME[index_ALL]
        DATA = DATA[:, index_ALL, :]
        CORCOEF = CORCOEF[:, index_ALL]
        
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # WARNING : From here on, STANAME has changed. A new index must
        #           be determined.
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        
        target_station_index = np.where(STANAME == self.TARGET.name)[0][0]

        #--------------------------------- Checks Variables With Enough Data --
        
        # NOTE: When a station does not have enough data for a given variable,
        #       its correlation coefficient is set to nan in CORCOEF. If all
        #       the stations have a value of nan in the correlation table for
        #       a given variable, it means there is not enough data available
        #       overall to estimate and fill missing data for it.
        
        var2fill = np.sum(~np.isnan(CORCOEF[:, :]), axis=1)
        var2fill = np.where(var2fill > 1)[0]
        
        for var in range(nVAR):
            if var not in var2fill:            
                msg = ('!Variable %d/%d won''t be filled because there ' +
                       'is not enough data!') % (var+1, nVAR)
                print(msg)
                self.ConsoleSignal.emit('<font color=red>%s</font>' % msg)
        
        #--------------------------------------------------------- FILL LOOP --

        FLAG_nan = False # If some missing data can't be completed because 
                         # all the neighboring stations are empty, a flag is
                         # raised and a comment is issued at the end of the 
                         # completion process.
        
        nbr_nan_total = np.isnan(Y2fill[index_start:index_end+1, var2fill])
        nbr_nan_total = np.sum(nbr_nan_total)

        if self.full_error_analysis == True:
            progress_total = np.size(Y2fill[:, var2fill])
        else:
            progress_total = np.copy(nbr_nan_total)
            
        fill_progress = 0
        
        # *progress_total* and *fill_progress* are used to display the task
        # progression on the UI progression bar.
        
        INFO_VAR = np.zeros(nbr_nan_total).astype('str')
        INFO_NSTA = np.zeros(nbr_nan_total).astype('float')
        INFO_RMSE = np.zeros(nbr_nan_total).astype('float')
        INFO_ROW = np.zeros(nbr_nan_total).astype('int')
        INFO_YEAR = np.zeros(nbr_nan_total).astype('int')
        INFO_MONTH = np.zeros(nbr_nan_total).astype('int')
        INFO_DAY =  np.zeros(nbr_nan_total).astype('int')
        INFO_YX = np.zeros((nbr_nan_total, len(STANAME))) * np.nan
        it_info = 0 # Number of missing data estimated iteration counter
        
        AVG_RMSE = np.zeros(nVAR).astype('float')
        AVG_NSTA = np.zeros(nVAR).astype('float')
        station_use_counter = np.zeros((nVAR, len(STANAME))).astype('int')
        
        for var in var2fill:
                                        
            msg = ('Data completion for variable %d/%d in progress' %
                   (var+1, nVAR))
            print msg
            
            colm_memory = np.array([]) # Column sequence memory matrix
            RegCoeff_memory = [] # Regression coefficient memory matrix
            RMSE_memory = []
            
            # Sort station in descending correlation coefficient order.
            # Target station index should be pulled at index 0 since its
            # correlation with itself is 1.
            Sta_index = sort_stations_correlation_order(CORCOEF[var, :],
                                                        target_station_index)
            
            # Data for this variable are stored in a 2D matrix where the raws
            # are the weather data of the current variable to fill for each
            # time frame and the columns are the weather station, arranged in
            # descending correlation order. Target station data serie should be
            # contained at j = 0.
            YX = np.copy(DATA[:, Sta_index, var])              
            
            # Find rows where data are missing between the date limits
            # that correspond to index_start and index_end
            row_nan = np.where(np.isnan(YX[:, 0]))[0]
            row_nan = row_nan[row_nan >= index_start]
            row_nan = row_nan[row_nan <= index_end]
            it_avg = 0 # counter used in the calculation of average RMSE
                       # and NSTA values.
            
            if self.full_error_analysis == True :
                row2fill = range(len(Y2fill[:, 0])) # All the data of the time 
                                                    # series will be estimated 
            else:
                row2fill = row_nan                
                                               
            for row in row2fill:
                
                sleep(0.000001) #If no sleep, the UI becomes whacked
                
                # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!                
                if self.STOP == True:
                    
                    msg = ('Completion process for station %s stopped.' %
                           target_station_name)
                    print(msg)
                    self.ConsoleSignal.emit('<font color=red>msg</font>')                    
                    self.STOP = False
                    
                    return                    
                # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                  
                # Find neighboring stations with valid entries at 
                # row <row> in <YX>. Target station is stored at index 0.
                colm = np.where(~np.isnan(YX[row, 1:]))[0]                    
                
                if np.size(colm) == 0:
                    
                    # Impossible to fill variable because all neighboring 
                    # stations are empty.
                    
                    if self.full_error_analysis == True:
                        YpFULL[row, var] = np.nan
                    
                    if row in row_nan:
                        Y2fill[row, var] = np.nan
                        
                        FLAG_nan = True # A warning comment will be issued at
                                        # the end of the completion process.
                        
                        INFO_VAR[it_info] = VARNAME[var]
                        INFO_NSTA[it_info] = np.nan
                        INFO_RMSE[it_info] = np.nan
                        INFO_ROW[it_info] = int(row)
                        INFO_YEAR[it_info] = str(int(YEAR[row]))
                        INFO_MONTH[it_info] = str(int(MONTH[row]))
                        INFO_DAY[it_info] =  DAY[row]
                        INFO_YX[it_info, :] = np.nan  
                        
                        it_info += 1
                else:
                    
                    # Neighboring stations are not empty, continue with the
                    # missing data estimation procedure for this row.
                
                    # Number of station to include in the regression model.
                    NSTA = min(len(colm), Nbr_Sta_max)
                    
                    # Remove superflux station from <colm>.
                    colm = colm[:NSTA]
                    
                    # Add an index 0 at index 0 to include the target
                    # station and correct index of the neighboring stations
                    colm = colm + 1
                    colm = np.insert(colm, 0, 0)
                    
                    # Store values of the independent variables 
                    # (neighboring stations) for this row in a new array.
                    # An intercept term is added if Var is temperature type
                    # variable, but not if it is precipitation type.
                    if var in (0, 1, 2):
                        X_row = np.hstack((1, YX[row, colm[1:]]))
                    else:
                        X_row = YX[row, colm[1:]]
                    
                    # Elements of the <colm> array are put back to back
                    # in a single string. For example, a [2, 7, 11] array
                    # would end up as '020711'. This allow to assign a
                    # unique number ID to a column combination. Each
                    # column correspond to a unique weather station.
                    
                    colm_seq = ''
                    for i in range(len(colm)):
                        colm_seq += '%02d' % colm[i]
                    
                    # A check is made to see if the current combination
                    # of neighboring stations has been encountered
                    # previously in the routine. Regression coefficients
                    # are calculated only once for a given neighboring
                    # station combination.
                    index_memory = np.where(colm_memory == colm_seq)[0]                                   
                    
                    if len(index_memory) == 0:
                        
                    # First time this neighboring station combination
                    # is encountered in the routine, regression
                    # coefficients are then calculated.
                    
                        # The memory is activated only if the option
                        # 'full_error_analysis' is not active. Otherwise, the
                        # memory remains empty and a new MLR model is built
                        # for each value of the data series.
                        if self.full_error_analysis != True: 
                            colm_memory = np.append(colm_memory, colm_seq)
                    
                        # Columns of DATA for the variable VAR are sorted
                        # in descending correlation coefficient and the 
                        # information is stored in a 2D matrix (The data for 
                        # the target station are included at index j=0).
                        YXcolm = np.copy(YX)       
                        YXcolm = YXcolm[:, colm]
                        
                        # Force the value of the target station to a NAN value
                        # for this row. This should only have an impact when 
                        # the option "full_error_analysis" is activated. This 
                        # is to actually remove the data being estimated 
                        # from the dataset like in should properly be done 
                        # in the jackknife procedure.
                        YXcolm[row, 0] = np.nan
                        
                        # All rows containing NAN entries are removed.
                        YXcolm = YXcolm[~np.isnan(YXcolm).any(axis=1)]
                    
                        # Rows for which precipitation of the target station
                        # and all neighboring station is 0 are removed. Only
                        # applicable for precipitation, not air temperature.
                        if var == 3:                        
                            YXcolm = YXcolm[~(YXcolm == 0).all(axis=1)]  
                                            
                        Y = YXcolm[:, 0]  # Dependant variable (target)                     
                        X = YXcolm[:, 1:] # Independant variables (neighbors)
                
                        # Add a unitary array to X for the intercept term if
                        # variable is a temperature type data.
                        if var in (0, 1, 2):
                            X = np.hstack((np.ones((len(Y), 1)), X))
                        else:
                            'Do not add an intercept term'
                    
                        if self.regression_mode == True:
                            # Ordinary Least Square regression
                            A = linalg_lstsq(X, Y)[0]
                        else:
                            # Least Absolute Deviations regression
                            A = L1LinearRegression(X, Y)
                            
                            # This section of the code is if I decide at
                            # some point to use this package instead of
                            # my own custom function.
                            
                            #model = sm.OLS(Y, X) 
                            #results = model.fit()
                            #print results.params
                            
                            #model = QuantReg(Y, X)
                            #results = model.fit(q=0.5)
                            #A = results.params
                            
                        #-------------------------------------- Compute RMSE --
                        
                        # Calculate a RMSE between the estimated and
                        # measured values of the target station.
                        # RMSE with 0 value are not accounted for
                        # in the calcultation.                        
                        
                        Yp = np.dot(A, X.transpose())
                        
                        RMSE = (Y - Yp)**2          # MAE = np.abs(Y - Yp)
                        RMSE = RMSE[RMSE != 0]      # MAE = MAE[MAE!=0]
                        RMSE = np.mean(RMSE)**0.5   # MAE = np.mean(MAE)
                        
                        RegCoeff_memory.append(A)
                        RMSE_memory.append(RMSE)
                    
                    else:
                        
                    # Regression coefficients and RSME are recalled
                    # from the memory matrices.

                        A = RegCoeff_memory[index_memory]
                        RMSE = RMSE_memory[index_memory]
                                            
                    #------------------------------ MISSING VALUE ESTIMATION --
                    
                    # Calculate missing value of Y at row <row>.
                    Y_row = np.dot(A, X_row)
                    
                    # Limit precipitation based variable to positive values.
                    # This may happens when there is one or more negative 
                    # regression coefficients in A
                    if var in (3, 4, 5):
                        Y_row = max(Y_row, 0)
                        
                    # Round the results.
                    Y_row = round(Y_row ,1)
                    
                    #----------------------------------------- STORE RESULTS --
                  
                    if self.full_error_analysis == True:
                        YpFULL[row, var] = Y_row
                        
                    if row in row_nan:
                        Y2fill[row, var] = Y_row

                        INFO_VAR[it_info] = VARNAME[var]
                        INFO_NSTA[it_info] = NSTA
                        INFO_RMSE[it_info] = RMSE
                        INFO_ROW[it_info] = int(row)
                        INFO_YEAR[it_info] = str(int(YEAR[row]))
                        INFO_MONTH[it_info] = str(int(MONTH[row]))
                        INFO_DAY[it_info] =  DAY[row]
                        
                        AVG_RMSE[var] += RMSE
                        AVG_NSTA[var] += NSTA
                        it_avg += 1
                        
                        Sta_index_row = Sta_index[colm]
                        if var in (0, 1, 2):                    
                            INFO_YX[it_info, Sta_index_row[0]] = Y_row
                            INFO_YX[it_info, Sta_index_row[1:]] = X_row[1:]
                        else:
                            INFO_YX[it_info, Sta_index_row[0]] = Y_row
                            INFO_YX[it_info, Sta_index_row[1:]] = X_row
                        
                        it_info += 1 # Total number of missing data counter    
                        
                        INFO_BOOLEAN = np.zeros(len(STANAME))
                        INFO_BOOLEAN[Sta_index_row] = 1
                        station_use_counter[var, :] += INFO_BOOLEAN
                    
                fill_progress += 1.
                self.ProgBarSignal.emit(fill_progress/progress_total * 100)
                
            #------------------ Calculate Estimation Error for this variable --
            
            if it_avg > 0:
                AVG_RMSE[var] /= it_avg
                AVG_NSTA[var] /= it_avg
            else:
                AVG_RMSE[var] = np.nan
                AVG_NSTA[var] = np.nan
                
            print_message = ('Data completion for variable %d/%d completed'
                             ) % (var+1, nVAR)
            print print_message             

        #================================================ WRITE DATA TO FILE ==
                    
        self.ConsoleSignal.emit('<font color=black>Data completion ' + 
                                'for station ' + target_station_name +
                                ' completed</font>')
                                
        if FLAG_nan == True:
            self.ConsoleSignal.emit(
                '<font color=red>WARNING: Some missing data were not ' +
                'completed because all neighboring station were empty ' +
                'for that period</font>')
    
        #------------------------------------------ INFO DATA POSTPROCESSING --
        
        # Put target station name and information to the begining of the
        # STANANE array and INFO matrix.
        INFO_Yname = STANAME[target_station_index]
        INFO_Y = INFO_YX[:, target_station_index].astype('str')
                    
        INFO_Xname = np.delete(STANAME, target_station_index)
        INFO_X = np.delete(INFO_YX, target_station_index, axis=1)
        
        station_use_counter = np.delete(station_use_counter,
                                        target_station_index, axis=1)

        # Check for neighboring stations that were used for filling data
        station_use_counter_total = np.sum(station_use_counter, axis=0)
        index = np.where(station_use_counter_total > 0)[0]
        
        # Keep only stations that were used for filling data
        INFO_Xname = INFO_Xname[index]
        INFO_X = INFO_X[:, index]
        station_use_counter_total = station_use_counter_total[index]
        station_use_counter = station_use_counter[:, index]
        
        # Sort neighboring stations by importance
        index = np.argsort(station_use_counter_total * -1)
        
        INFO_Xname = INFO_Xname[index]
        INFO_X = INFO_X[:, index]
        
        station_use_counter_total = station_use_counter_total[index]
        station_use_counter = station_use_counter[:, index]
        
        # Replace nan values by ''
        INFO_X = INFO_X.astype('str')
        INFO_X[INFO_X == 'nan'] = ''
       
        #------------------------------------------------------------ HEADER --
              
        HEADER = [['Station Name', target_station_name]]
        HEADER.append(['Province', target_station_prov])
        HEADER.append(['Latitude', target_station_lat])
        HEADER.append(['Longitude', target_station_lon])
        HEADER.append(['Elevation', target_station_alt])
        HEADER.append(['Climate Identifier', target_station_clim])
        HEADER.append([])
        HEADER.append(['Created by', db.software_version])
        HEADER.append(['Created on', strftime("%d/%m/%Y")])
        HEADER.append([])
        
        #---------------------------------------------------- LOG GENERATION --
        
        record_date_start = '%04d/%02d/%02d' % (YEAR[index_start],
                                                MONTH[index_start],
                                                DAY[index_start]) 
                                            
        record_date_end = '%04d/%02d/%02d' % (YEAR[index_end],
                                              MONTH[index_end],
                                              DAY[index_end])
        
        INFO_total = copy(HEADER)
        
        INFO_total.append(['*** FILL PROCEDURE INFO ***'])
        
        INFO_total.append([])
        if self.regression_mode == True:
            INFO_total.append(['MLR model', 'Ordinary Least Square'])
        elif self.regression_mode == False:
            INFO_total.append(['MLR model', 'Least Absolute Deviations'])
        INFO_total.append(['Precip correction', 'Not Available'])
        INFO_total.append(['Wet days correction', 'Not Available'])
        INFO_total.append(['Max number of stations', str(Nbr_Sta_max)])
        INFO_total.append(['Cutoff distance (km)', str(limitDist)])
        INFO_total.append(['Cutoff altitude difference (m)', str(limitAlt)])
        INFO_total.append(['Date Start', record_date_start])
        INFO_total.append(['Date End', record_date_end])
        INFO_total.append([])
        INFO_total.append([])
                    
        INFO_total.append(['*** SUMMARY TABLE ***'])
        
        INFO_total.append([])
        INFO_total.append(['CLIMATE VARIABLE', 'TOTAL MISSING',
                           'TOTAL FILLED', '', 'AVG. NBR STA.',
                           'AVG. RMSE', ''])
        INFO_total[-1].extend(INFO_Xname)
        
        total_nbr_data = index_end - index_start + 1
        nbr_fill_total = 0
        nbr_nan_total = 0
        for var in range(nVAR):
            
            nbr_nan = np.isnan(DATA[index_start:index_end+1,
                                    target_station_index, var])
            nbr_nan = float(np.sum(nbr_nan))
            
            nbr_nan_total += nbr_nan
            
            nbr_nofill = np.isnan(Y2fill[index_start:index_end+1, var])
            nbr_nofill = np.sum(nbr_nofill)
            
            nbr_fill = nbr_nan - nbr_nofill
            
            nbr_fill_total += nbr_fill
            
            nan_percent = round(nbr_nan / total_nbr_data * 100, 1)
            if nbr_nan != 0:
                nofill_percent = round(nbr_nofill / nbr_nan * 100, 1)
                fill_percent = round(nbr_fill / nbr_nan * 100, 1)
            else:
                nofill_percent = 0
                fill_percent = 100
            
            nbr_nan = '%d (%0.1f %% of total)' % (nbr_nan, nan_percent)
 
            nbr_nofill = '%d (%0.1f %% of missing)' % (nbr_nofill,
                                                       nofill_percent)

            nbr_fill_txt = '%d (%0.1f %% of missing)' % (nbr_fill,
                                                         fill_percent)
       
            INFO_total.append([VARNAME[var], nbr_nan, nbr_fill_txt, '',
                               '%0.1f' % AVG_NSTA[var],
                               '%0.2f' % AVG_RMSE[var], ''])

            for i in range(len(station_use_counter[0, :])):
                percentage = round(
                            station_use_counter[var, i] / nbr_fill * 100, 1)
                           
                INFO_total[-1].extend([
                '%d (%0.1f %% of filled)' % (station_use_counter[var, i],
                                             percentage)])

        nbr_fill_percent = round(nbr_fill_total / nbr_nan_total * 100, 1)
        nbr_fill_total_txt = '%d (%0.1f %% of missing)' % \
                                          (nbr_fill_total, nbr_fill_percent)
        
        nan_total_percent = round(
                           nbr_nan_total / (total_nbr_data * nVAR) * 100, 1)
        nbr_nan_total = '%d (%0.1f %% of total)' % (nbr_nan_total,
                                                    nan_total_percent)
        INFO_total.append([])
        INFO_total.append(['TOTAL', nbr_nan_total, nbr_fill_total_txt, 
                          '', '---', '---', ''])
        for i in range(len(station_use_counter_total)):
                percentage = round(
                     station_use_counter_total[i] / nbr_fill_total * 100, 1)
                text2add = '%d (%0.1f %% of filled)' \
                                % (station_use_counter_total[i], percentage)
                INFO_total[-1].extend([text2add])            
        INFO_total.append([])
        INFO_total.append([])
        
        INFO_total.append(['*** DETAILED REPORT ***'])
        
        INFO_total.append([])
        INFO_total.append(['VARIABLE', 'YEAR', 'MONTH', 'DAY',
                           'NBR STA.','RMSE'])
        INFO_total[-1].extend([INFO_Yname])
        INFO_total[-1].extend(INFO_Xname)
        INFO_ROW = INFO_ROW.tolist()
        INFO_RMSE = np.round(INFO_RMSE, 2).astype('str')
        for i in range(len(INFO_Y)):
            info_row_builder = [INFO_VAR[i], INFO_YEAR[i], INFO_MONTH[i],
                                '%d' % INFO_DAY[i], '%0.0f' % INFO_NSTA[i],
                                INFO_RMSE[i], INFO_Y[i]]
            info_row_builder.extend(INFO_X[i])
            
            INFO_total.append(info_row_builder)
                
        #--------------------------------------------------------- SAVE INFO --
                                  
        YearStart = str(int(YEAR[index_start])) 
        YearEnd = str(int(YEAR[index_end]))

        # Check if the characters "/" or "\" are present in the station 
        # name and replace these characters by "-" if applicable.
        
        target_station_name = target_station_name.replace('\\', '_')
        target_station_name = target_station_name.replace('/', '_')

        output_path = (self.project_dir + '/Meteo/Output/' + 
                       target_station_name + ' (' + target_station_clim +
                       ')'+ '_' + YearStart + '-' +  YearEnd + '.log')
        
        with open(output_path, 'w') as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerows(INFO_total)
        
        self.ConsoleSignal.emit(
            '<font color=black>Info file saved in ' + output_path +
            '</font>')
            
        #--------------------------------------------------------- SAVE DATA --
        
        DATA2SAVE = copy(HEADER)
        DATA2SAVE.append(['Year', 'Month', 'Day'])
        DATA2SAVE[-1].extend(VARNAME)
               
        ALLDATA = np.vstack((YEAR[index_start:index_end+1],
                             MONTH[index_start:index_end+1],
                             DAY[index_start:index_end+1], 
                             Y2fill[index_start:index_end+1].transpose())
                             ).transpose()
        ALLDATA.tolist() 
        for i in range(len(ALLDATA)):
            DATA2SAVE.append(ALLDATA[i])
        
        output_path = (self.project_dir + '/Meteo/Output/' + 
                       target_station_name + ' (' + target_station_clim +
                       ')'+ '_' + YearStart + '-' +  YearEnd + '.out')
        
        with open(output_path, 'w') as f:
            writer = csv.writer(f,delimiter='\t')
            writer.writerows(DATA2SAVE)
            
        if self.add_ETP:
            meteo.add_ETP_to_weather_data_file(output_path)            
        
        self.ConsoleSignal.emit('<font color=black>Meteo data saved in ' +
                                output_path + '</font>')
        self.ProgBarSignal.emit(0)
        
        #---------------------------------------- SAVE ERROR ANALYSIS REPORT --
        
        if self.full_error_analysis == True:
            
            error_analysis_report = copy(HEADER)
            error_analysis_report.append(['Year', 'Month', 'Day'])
            error_analysis_report[-1].extend(VARNAME)
            
            ALLDATA = np.vstack((YEAR, MONTH, DAY, YpFULL.transpose()))
            ALLDATA = ALLDATA.transpose()                 
            ALLDATA.tolist() 
            for i in range(len(ALLDATA)):
                error_analysis_report.append(ALLDATA[i])
            
            output_path = (self.project_dir + '/Meteo/Output/' + 
                       target_station_name + ' (' + target_station_clim +
                       ')'+ '_' + YearStart + '-' +  YearEnd + '.err')
                           
            with open(output_path, 'w') as f:
                writer = csv.writer(f,delimiter='\t')
                writer.writerows(error_analysis_report)
        
            #--------------------------------------------- SOME CALCULATIONS --
            
            RMSE = np.zeros(nVAR)
            ERRMAX  = np.zeros(nVAR)
            ERRSUM = np.zeros(nVAR)
            for i in range(nVAR):
                errors = YpFULL[:, i] - Y2fill[:, i]
                
                rmse = errors**2 
                rmse = rmse[rmse != 0]                  
                rmse = np.mean(rmse)**0.5
                
                errmax = np.abs(errors)
                errmax = np.max(errmax)
                
                errsum = np.sum(errors)
                
                
                RMSE[i] = rmse
                ERRMAX[i] = errmax
                ERRSUM[i] = errsum
            
            print(RMSE)
            print(ERRMAX)
            print(ERRSUM)
            
            DIFF = np.abs(YpFULL- Y2fill)
            index = np.where(DIFF[:, -1] == ERRMAX[-1])
            print YEAR[index], MONTH[index], DAY[index]
        
        print; print('!Data completion completed successfully!'); print                 
        self.STOP = False # Just in case. This is a precaution override.  
        self.EndProcess.emit(1) 
        
        return
        
#==============================================================================
def sort_stations_correlation_order(CORCOEF, target_station_index): 
#==============================================================================
        
    # An index is associated with each value of the CORCOEF array.
    Sta_index = range(len(CORCOEF))    
    CORCOEF = np.vstack((Sta_index, CORCOEF)).transpose()
    
    # Remove target station from the stack. This is necessary in case there is
    # some data that belong to the same station, but without the same length.
    
    CORCOEF = np.delete(CORCOEF, target_station_index, axis=0)
    
    # Stations for which the correlation coefficient is nan are removed.
    CORCOEF = CORCOEF[~np.isnan(CORCOEF).any(axis=1)] 
               
    # The station indexes are sorted in descending order of their
    # correlation coefficient.
    CORCOEF = CORCOEF[np.flipud(np.argsort(CORCOEF[:, 1])), :]
    
    Sta_index = np.copy(CORCOEF[:, 0].astype('int'))
    
    # Add target station to the first value of the array.
    Sta_index = np.insert(Sta_index, 0, target_station_index)
    
    return Sta_index
        
#==============================================================================    
def L1LinearRegression(X, Y): 
    """
    L1LinearRegression: Calculates L-1 multiple linear regression by IRLS
    (Iterative reweighted least squares)

    B = L1LinearRegression(Y,X)

    B = discovered linear coefficients 
    X = independent variables 
    Y = dependent variable 

    Note 1: An intercept term is NOT assumed (need to append a unit column if
            needed). 
    Note 2: a.k.a. LAD, LAE, LAR, LAV, least absolute, etc. regression 

    SOURCE:
    This function is originally from a Matlab code written by Will Dwinnell
    www.matlabdatamining.blogspot.ca/2007/10/l-1-linear-regression.html
    Last accessed on 21/07/2014
    """
#==============================================================================
 
    # Determine size of predictor data.
    n, m = np.shape(X)
    
    # Initialize with least-squares fit.
    B = linalg_lstsq(X, Y)[0]                               
    BOld = np.copy(B) 
    
    # Force divergence.
    BOld[0] += 1e-5

    # Repeat until convergence.
    while np.max(np.abs(B - BOld)) > 1e-6:
         
        BOld = np.copy(B)
        
        # Calculate new observation weights based on residuals from old 
        # coefficients. 
        weight =  np.dot(B, X.transpose()) - Y
        weight =  np.abs(weight)
        weight[weight < 1e-6] = 1e-6 # to avoid division by zero
        weight = weight**-0.5
        
        # Calculate new coefficients.
        Xb = np.tile(weight, (m, 1)).transpose() * X      
        Yb = weight * Y
        
        B = linalg_lstsq(Xb, Yb)[0]
        
    return B
        
if __name__ == '__main__':
    print('Testing code not implemented yet because the structure')
    print('of the code does not allow it yet.')