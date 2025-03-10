from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd
import os
from datetime import datetime
from flask import send_from_directory
import platform
import subprocess

app = Flask(__name__)

# Define the path to store CSV files
CSV_FILE_PATH = 'data/expenses.csv'

def preprocess_data():
    try:
        
        # Load data from CSV
        df = pd.read_csv(CSV_FILE_PATH)

        # Ensure the column containing month-year is parsed correctly
        df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], errors='coerce')

        # Extract month and year for sorting purposes
        df['Month-Year'] = df['Transaction Date'].dt.to_period('M').astype(str)

        # Group data by month-year
        grouped = df.groupby('Month-Year').apply(
            lambda x: x.groupby('Category')['CAD$'].sum().to_dict()
        ).to_dict()

        # Sort by month-year in descending order
        sorted_grouped = dict(sorted(grouped.items(), key=lambda x: pd.Period(x[0], freq='M'), reverse=True))
        
        return sorted_grouped
    
    except FileNotFoundError:
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and file.filename.endswith('.csv'):
        try:
            # Load the uploaded CSV into a DataFrame
            # df = pd.read_csv(file)
            df = pd.read_csv(file, quotechar='"', skipinitialspace=True)

            # print(df.head())

            # Filter and transform rows based on conditions
            filtered_df = []
            for index, row in df.iterrows():
                description_2 = str(row['Description 2'])
                # print(description_2)
                cad_amount = float(row['CAD$'])

                if ("Your Insurance Company" in description_2):
                    category = "Insurance"
                elif ("MORTGAGEPROTECT" in description_2):
                    category = "Mortgage Protection"
                elif ("PROPERTY TAX" in description_2):
                    category = "Property Tax"
                elif ("UTILITIES" in description_2):
                    category = "Utility"
                elif ("Your Bank" in description_2):
                    category = "Mortgage"
                elif ("Your City Electricity Company" in description_2):
                    if cad_amount < 0:
                        category = "Electricity"
                    else:
                        category = "Solar Gen"
                else:
                    continue

                filtered_df.append({
                    'Account Type': row['Account Type'],
                    'Account Number': row['Account Number'],
                    'Transaction Date': row['Transaction Date'],
                    'Cheque Number': row['Cheque Number'],
                    'Description 1': row['Description 1'],
                    'Description 2': row['Description 2'],
                    'CAD$': row['CAD$'],
                    'USD$': row['USD$'],
                    'Category': category
                })

            filtered_df = pd.DataFrame(filtered_df)

            # Append the new data to the existing CSV file (or create it if it doesn't exist)
            if os.path.exists(CSV_FILE_PATH):
                existing_df = pd.read_csv(CSV_FILE_PATH)
                df = existing_df.append(filtered_df, ignore_index=True)
            else:
                df = filtered_df

            df.to_csv(CSV_FILE_PATH, index=False)
            return jsonify({'message': 'File uploaded successfully'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/data', methods=['GET'])
def get_data():
    expenses_dict = preprocess_data()
    
    if expenses_dict is not None:
        return jsonify(expenses_dict), 200
    else:
        empty_dict = {}
        return jsonify(empty_dict), 404

@app.route('/add_expense', methods=['POST'])
def add_expense():
    category = request.form['category']
    date = request.form['date']
    amount = float(request.form['amount'])
    is_income = request.form['expense_or_income'] == 'Income'
    note = request.form['note']
    if not note:
        note = " "

    # Convert date to the required format
    formatted_date = datetime.strptime(date, '%Y-%m-%d').strftime('%m/%d/%Y')
    
    expense_data = {
        'Category': [category],
        'Account Type': ['Chequing'],
        'Account Number': [''],
        'Transaction Date': [formatted_date],
        'Cheque Number': [''],
        'Description 1': [''],
        'Description 2': [note],
        'CAD$': [amount if is_income else -amount],
        'USD$': [0]  # Optional, depending on your requirements
    }

    # Append to CSV
    if os.path.exists(CSV_FILE_PATH):
        existing_df = pd.read_csv(CSV_FILE_PATH)
        new_df = pd.DataFrame(expense_data)
        updated_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        updated_df = pd.DataFrame(expense_data)

    updated_df.to_csv(CSV_FILE_PATH, index=False)
    return jsonify({'message': 'Expense added successfully'})

@app.route('/statistics', methods=['POST'])
def statistics():
    period = request.form['period']
    df = pd.read_csv(CSV_FILE_PATH)

    # Convert 'Transaction Date' column to datetime format with the correct format
    df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], format='%m/%d/%Y')

    # Filter by period (3 months, 6 months, 1 year, or All dates)
    if period == '3 months':
        start_date = pd.Timestamp.now() - pd.DateOffset(months=3)
    elif period == '6 months':
        start_date = pd.Timestamp.now() - pd.DateOffset(months=6)
    elif period == '1 year':
        start_date = pd.Timestamp.now() - pd.DateOffset(years=1)
    elif period == 'All':
        start_date = pd.Timestamp.now() - pd.DateOffset(years=100)
    
    # Filter dataframe based on the start date
    df = df[df['Transaction Date'] >= start_date]

    # Find the number of unique months in the filtered data
    months_in_period = len(df['Transaction Date'].dt.to_period('M').unique())

    # Group by category and calculate sum of CAD$
    category_sums = df.groupby('Category')['CAD$'].sum()

    # Calculate average per month by dividing by months_in_period
    category_avg = category_sums / months_in_period

    # Convert the result into a dictionary
    category_avg_dict = category_avg.to_dict()

    return jsonify(category_avg_dict), 200

@app.route('/all_expenses', methods=['GET'])
def all_expenses():
    try:
        # Read the data from the CSV
        df = pd.read_csv(CSV_FILE_PATH)
        
        # Replace missing values with an empty string
        df.fillna("", inplace=True)
        
        # Ensure the 'Transaction Date' is parsed correctly as datetime
        df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], errors='coerce')

        # Drop rows with invalid 'Transaction Date' if needed
        df.dropna(subset=['Transaction Date'], inplace=True)

        # Sort the DataFrame by 'Transaction Date' in descending order
        df.sort_values(by='Transaction Date', ascending=False, inplace=True)

        # Format 'Transaction Date' as '%m/%d/%Y'
        df['Transaction Date'] = df['Transaction Date'].dt.strftime('%m/%d/%Y')

        # Select only the required columns
        df = df[['Transaction Date', 'Description 1', 'Description 2', 'CAD$', 'Category']]

        # Convert the DataFrame to a dictionary
        data = df.to_dict(orient='records')

        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})
    
@app.route('/open_directory', methods=['GET'])
def open_directory():
    try:
        directory = os.path.dirname(os.path.abspath(CSV_FILE_PATH))
        
        if platform.system() == 'Windows':
            os.startfile(directory)
        elif platform.system() == 'Darwin':  # macOS
            subprocess.Popen(['open', directory])
        else:  # Linux
            subprocess.Popen(['xdg-open', directory])

        return jsonify({"status": "success", "message": "Directory opened successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(debug=True)  