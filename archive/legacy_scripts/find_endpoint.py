def find():
    try:
        with open(r'e:\Work\Code\AINEWS\backend\main.py', 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if '/api/public/news' in line:
                    print(i)
                    return
    except:
        pass

if __name__ == "__main__":
    find()
