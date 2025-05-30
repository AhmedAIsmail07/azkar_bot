import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime

class GoogleSheetsIntegration:
    def __init__(self, credentials_file):
        """
        Initialize Google Sheets integration with the provided credentials file
        
        Args:
            credentials_file (str): Path to the service account credentials JSON file
        """
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=self.SCOPES)
        self.service = build('sheets', 'v4', credentials=self.credentials)
        self.sheets = self.service.spreadsheets()
        
        # Google Sheet ID from the provided link
        self.SPREADSHEET_ID = '1XDAqhMa_N9iThRotfylOzkgKhkNoq1EdliM2qCz2Qgo'
        
        # Sheet names
        self.USER_DATA_SHEET = 'user_data'
        self.QURAN_TRACKING_SHEET = 'quran_tracking'
        
        # Ensure sheets exist
        self._ensure_sheets_exist()
    
    def _ensure_sheets_exist(self):
        """Ensure that required sheets exist, create them if they don't"""
        try:
            # Get existing sheets
            sheet_metadata = self.sheets.get(spreadsheetId=self.SPREADSHEET_ID).execute()
            sheets = sheet_metadata.get('sheets', [])
            existing_sheets = [sheet['properties']['title'] for sheet in sheets]
            
            # Check if user_data sheet exists
            if self.USER_DATA_SHEET not in existing_sheets:
                self._create_user_data_sheet()
            
            # Check if quran_tracking sheet exists
            if self.QURAN_TRACKING_SHEET not in existing_sheets:
                self._create_quran_tracking_sheet()
                
        except Exception as e:
            print(f"Error ensuring sheets exist: {e}")
    
    def _create_user_data_sheet(self):
        """Create the user_data sheet with appropriate headers"""
        try:
            # Add new sheet
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': self.USER_DATA_SHEET
                        }
                    }
                }]
            }
            self.sheets.batchUpdate(spreadsheetId=self.SPREADSHEET_ID, body=body).execute()
            
            # Add headers
            headers = [
                'user_id', 'username', 'first_name', 'last_name', 'join_date',
                'quran_service', 'prayer_service', 'dhikr_service', 'qiyam_service',
                'last_quran_page', 'pending_quran_pages', 'read_confirmation', 'last_update'
            ]
            
            values = [headers]
            body = {'values': values}
            self.sheets.values().update(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.USER_DATA_SHEET}!A1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
        except Exception as e:
            print(f"Error creating user_data sheet: {e}")
    
    def _create_quran_tracking_sheet(self):
        """Create the quran_tracking sheet with appropriate headers"""
        try:
            # Add new sheet
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': self.QURAN_TRACKING_SHEET
                        }
                    }
                }]
            }
            self.sheets.batchUpdate(spreadsheetId=self.SPREADSHEET_ID, body=body).execute()
            
            # Add headers
            headers = [
                'user_id', 'username', 'total_pages_read', 'current_position',
                'last_batch_sent', 'last_batch_confirmed', 'pending_pages', 'last_update'
            ]
            
            values = [headers]
            body = {'values': values}
            self.sheets.values().update(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.QURAN_TRACKING_SHEET}!A1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
        except Exception as e:
            print(f"Error creating quran_tracking sheet: {e}")
    
    def get_user_data(self, user_id):
        """
        Get user data from the user_data sheet
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            dict: User data or None if not found
        """
        try:
            # Get all user data
            result = self.sheets.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.USER_DATA_SHEET}!A:M'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return None
                
            # Get headers
            headers = values[0]
            
            # Find user by user_id
            for row in values[1:]:  # Skip header row
                if row and str(row[0]) == str(user_id):
                    # Create dict from headers and row data
                    user_data = {}
                    for i, header in enumerate(headers):
                        user_data[header] = row[i] if i < len(row) else None
                    return user_data
            
            return None
            
        except Exception as e:
            print(f"Error getting user data: {e}")
            return None
    
    def add_or_update_user(self, user_data):
        """
        Add or update user in the user_data sheet
        
        Args:
            user_data (dict): User data to add or update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if user exists
            existing_user = self.get_user_data(user_data['user_id'])
            
            # Get all user data to find the row index
            result = self.sheets.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.USER_DATA_SHEET}!A:A'
            ).execute()
            
            values = result.get('values', [])
            
            # Add current timestamp
            user_data['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if existing_user:
                # Find the row index
                row_index = None
                for i, row in enumerate(values):
                    if row and str(row[0]) == str(user_data['user_id']):
                        row_index = i + 1  # +1 because sheets are 1-indexed
                        break
                
                if row_index:
                    # Get headers to ensure correct order
                    headers_result = self.sheets.values().get(
                        spreadsheetId=self.SPREADSHEET_ID,
                        range=f'{self.USER_DATA_SHEET}!1:1'
                    ).execute()
                    
                    headers = headers_result.get('values', [[]])[0]
                    
                    # Create row with data in the correct order
                    row_data = []
                    for header in headers:
                        row_data.append(user_data.get(header, ''))
                    
                    # Update the row
                    body = {'values': [row_data]}
                    self.sheets.values().update(
                        spreadsheetId=self.SPREADSHEET_ID,
                        range=f'{self.USER_DATA_SHEET}!A{row_index}',
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    
                    return True
            else:
                # Add new user
                # Get headers to ensure correct order
                headers_result = self.sheets.values().get(
                    spreadsheetId=self.SPREADSHEET_ID,
                    range=f'{self.USER_DATA_SHEET}!1:1'
                ).execute()
                
                headers = headers_result.get('values', [[]])[0]
                
                # Create row with data in the correct order
                row_data = []
                for header in headers:
                    row_data.append(user_data.get(header, ''))
                
                # Append the row
                body = {'values': [row_data]}
                self.sheets.values().append(
                    spreadsheetId=self.SPREADSHEET_ID,
                    range=f'{self.USER_DATA_SHEET}!A:A',
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
                
                return True
                
            return False
            
        except Exception as e:
            print(f"Error adding or updating user: {e}")
            return False
    
    def get_quran_tracking(self, user_id):
        """
        Get Quran tracking data for a user
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            dict: Quran tracking data or None if not found
        """
        try:
            # Get all tracking data
            result = self.sheets.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.QURAN_TRACKING_SHEET}!A:H'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return None
                
            # Get headers
            headers = values[0]
            
            # Find user by user_id
            for row in values[1:]:  # Skip header row
                if row and str(row[0]) == str(user_id):
                    # Create dict from headers and row data
                    tracking_data = {}
                    for i, header in enumerate(headers):
                        tracking_data[header] = row[i] if i < len(row) else None
                    return tracking_data
            
            return None
            
        except Exception as e:
            print(f"Error getting Quran tracking data: {e}")
            return None
    
    def update_quran_tracking(self, tracking_data):
        """
        Update Quran tracking data for a user
        
        Args:
            tracking_data (dict): Tracking data to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if tracking exists
            existing_tracking = self.get_quran_tracking(tracking_data['user_id'])
            
            # Get all tracking data to find the row index
            result = self.sheets.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.QURAN_TRACKING_SHEET}!A:A'
            ).execute()
            
            values = result.get('values', [])
            
            # Add current timestamp
            tracking_data['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if existing_tracking:
                # Find the row index
                row_index = None
                for i, row in enumerate(values):
                    if row and str(row[0]) == str(tracking_data['user_id']):
                        row_index = i + 1  # +1 because sheets are 1-indexed
                        break
                
                if row_index:
                    # Get headers to ensure correct order
                    headers_result = self.sheets.values().get(
                        spreadsheetId=self.SPREADSHEET_ID,
                        range=f'{self.QURAN_TRACKING_SHEET}!1:1'
                    ).execute()
                    
                    headers = headers_result.get('values', [[]])[0]
                    
                    # Create row with data in the correct order
                    row_data = []
                    for header in headers:
                        row_data.append(tracking_data.get(header, ''))
                    
                    # Update the row
                    body = {'values': [row_data]}
                    self.sheets.values().update(
                        spreadsheetId=self.SPREADSHEET_ID,
                        range=f'{self.QURAN_TRACKING_SHEET}!A{row_index}',
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    
                    return True
            else:
                # Add new tracking
                # Get headers to ensure correct order
                headers_result = self.sheets.values().get(
                    spreadsheetId=self.SPREADSHEET_ID,
                    range=f'{self.QURAN_TRACKING_SHEET}!1:1'
                ).execute()
                
                headers = headers_result.get('values', [[]])[0]
                
                # Create row with data in the correct order
                row_data = []
                for header in headers:
                    row_data.append(tracking_data.get(header, ''))
                
                # Append the row
                body = {'values': [row_data]}
                self.sheets.values().append(
                    spreadsheetId=self.SPREADSHEET_ID,
                    range=f'{self.QURAN_TRACKING_SHEET}!A:A',
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
                
                return True
                
            return False
            
        except Exception as e:
            print(f"Error updating Quran tracking data: {e}")
            return False
    
    def get_all_users(self):
        """
        Get all users from the user_data sheet
        
        Returns:
            list: List of user data dictionaries
        """
        try:
            # Get all user data
            result = self.sheets.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.USER_DATA_SHEET}!A:M'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return []
                
            # Get headers
            headers = values[0]
            
            # Create list of user data dictionaries
            users = []
            for row in values[1:]:  # Skip header row
                if row:
                    user_data = {}
                    for i, header in enumerate(headers):
                        user_data[header] = row[i] if i < len(row) else None
                    users.append(user_data)
            
            return users
            
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []
    
    def get_users_count(self):
        """
        Get the count of users in the user_data sheet
        
        Returns:
            int: Number of users
        """
        try:
            # Get all user data
            result = self.sheets.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=f'{self.USER_DATA_SHEET}!A:A'
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return 0
                
            # Subtract 1 for the header row
            return max(0, len(values) - 1)
            
        except Exception as e:
            print(f"Error getting users count: {e}")
            return 0
    
    def get_users_by_service(self, service_name):
        """
        Get all users subscribed to a specific service
        
        Args:
            service_name (str): Service name (quran_service, prayer_service, dhikr_service, qiyam_service)
            
        Returns:
            list: List of user data dictionaries
        """
        try:
            # Get all users
            users = self.get_all_users()
            
            # Filter users by service
            return [user for user in users if user.get(service_name) == 'True']
            
        except Exception as e:
            print(f"Error getting users by service: {e}")
            return []
